#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
applications_dir="$HOME/Applications"
app_bundle="$applications_dir/AI Usage Widget.app"
build_dir="$repo_dir/build/macos"
build_venv="$build_dir/.venv"
dist_dir="$build_dir/dist"
work_dir="$build_dir/work"
icon_file="$build_dir/AIUsageWidget.icns"
widget_build_dir="$build_dir/widget"
widget_project="$repo_dir/packaging/macos/widget-host/AIUsageWidgetHost.xcodeproj"
widget_derived_data="$widget_build_dir/DerivedData"
widget_bundle="$widget_derived_data/Build/Products/Release/AIUsageWidgetExtension.appex"
xcode_host_bundle="$widget_derived_data/Build/Products/Release/AI Usage Widget.app"
lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

macos_major=$(sw_vers -productVersion | cut -d. -f1)
if [ "$macos_major" -lt 14 ]; then
    echo "macOS 14 Sonoma or newer is required."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/macos/"
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "Python 3.10 or newer is required."
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "This Python installation does not include Tkinter."
    echo "Install Python from python.org, or install the matching python-tk package with Homebrew."
    exit 1
fi

widget_build=false
sign_identity=""
bundle_id="com.ulrichlab.ai-usage-widget"
developer_dir=$(xcode-select -p 2>/dev/null || true)

case "$developer_dir" in
    *.app/Contents/Developer)
        if xcodebuild -version >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then
            sign_identity=$(security find-identity -v -p codesigning | sed -n 's/.*"\(Apple Development:[^"]*\)".*/\1/p' | head -1)
            if [ -z "$sign_identity" ]; then
                sign_identity=$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)
            fi
            sign_team=$(printf '%s' "$sign_identity" | sed -n 's/.*(\([^()]*\))$/\1/p')
            if [ -n "$sign_team" ]; then
                widget_build=true
                bundle_suffix=$(printf '%s' "$sign_team" | tr '[:upper:]' '[:lower:]')
                bundle_id="com.ulrichlab.ai-usage-widget.$bundle_suffix"
            fi
        fi
        ;;
esac

if [ "$widget_build" = true ]; then
    echo "Building AI Usage Widget app and WidgetKit extension..."
else
    echo "Building AI Usage Widget app only (Xcode and a signing certificate are optional for the desktop widget)."
fi

mkdir -p "$build_dir" "$applications_dir"
python3 -m venv "$build_venv"
"$build_venv/bin/python" -m pip install --quiet --disable-pip-version-check \
    -r "$repo_dir/requirements-macos.txt" pyinstaller
"$build_venv/bin/python" "$repo_dir/packaging/macos/generate_icon.py" "$icon_file"

rm -rf "$dist_dir" "$work_dir"
set -- "$build_venv/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "AI Usage Widget" \
    --icon "$icon_file" \
    --osx-bundle-identifier "$bundle_id" \
    --hidden-import "pystray._darwin"
if [ "$widget_build" = true ]; then
    set -- "$@" --codesign-identity "$sign_identity"
fi
set -- "$@" \
    --distpath "$dist_dir" \
    --workpath "$work_dir" \
    --specpath "$build_dir" \
    "$repo_dir/src/ai_usage_widget_macos.py"
"$@"

built_app="$dist_dir/AI Usage Widget.app"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName AI Usage Widget" "$built_app/Contents/Info.plist"
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.1.4" "$built_app/Contents/Info.plist"; then
	/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.1.4" "$built_app/Contents/Info.plist"
fi
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleVersion 9" "$built_app/Contents/Info.plist"; then
	/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 9" "$built_app/Contents/Info.plist"
fi
/usr/libexec/PlistBuddy -c "Add :NSPrincipalClass string NSApplication" "$built_app/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :LSUIElement" "$built_app/Contents/Info.plist" 2>/dev/null || true

if [ "$widget_build" = true ]; then
    rm -rf "$widget_build_dir"
    xcodebuild \
	-project "$widget_project" \
	-scheme AIUsageWidgetHost \
	-configuration Release \
	-derivedDataPath "$widget_derived_data" \
	-allowProvisioningUpdates \
	DEVELOPMENT_TEAM="$sign_team" \
	AI_USAGE_BUNDLE_SUFFIX="$bundle_suffix" \
	CODE_SIGN_IDENTITY="$sign_identity" \
	build
    # xcodebuild registers its temporary host automatically. Remove that duplicate so
    # WidgetKit only sees the extension inside the app that is actually installed.
    pluginkit -r "$xcode_host_bundle/Contents/PlugIns/AIUsageWidgetExtension.appex" 2>/dev/null || true
    pluginkit -r "$widget_bundle" 2>/dev/null || true
    "$lsregister" -u "$xcode_host_bundle" 2>/dev/null || true
    mkdir -p "$built_app/Contents/PlugIns"
    ditto "$widget_bundle" "$built_app/Contents/PlugIns/AIUsageWidgetExtension.appex"
    codesign --force --sign "$sign_identity" "$built_app"
fi

if [ -d "$app_bundle" ]; then
    pluginkit -r "$app_bundle/Contents/PlugIns/AIUsageWidgetExtension.appex" 2>/dev/null || true
    "$lsregister" -u "$app_bundle" 2>/dev/null || true
fi
rm -rf "$app_bundle"
ditto "$built_app" "$app_bundle"
xattr -dr com.apple.quarantine "$app_bundle" 2>/dev/null || true
if [ "$widget_build" = true ]; then
    codesign --verify --deep --strict "$app_bundle"
fi

"$lsregister" -f "$app_bundle"
if [ "$widget_build" = true ]; then
    pluginkit -a "$app_bundle/Contents/PlugIns/AIUsageWidgetExtension.appex"
fi

echo "Installed successfully: $app_bundle"
if [ "$widget_build" != true ]; then
    echo "Desktop widget not installed. Install full Xcode and an Apple Development certificate, then run this installer again to add it."
fi
echo "Opening AI Usage Widget..."
open "$app_bundle"
