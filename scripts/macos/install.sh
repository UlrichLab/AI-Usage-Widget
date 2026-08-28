#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
install_dir="$HOME/Library/Application Support/AIUsageWidget"
applications_dir="$HOME/Applications"
app_bundle="$applications_dir/AI Usage Widget.app"

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

echo "Installing AI Usage Widget for macOS..."

mkdir -p "$install_dir" "$app_bundle/Contents/MacOS" "$applications_dir"
rm -rf "$install_dir/src"
cp -R "$repo_dir/src" "$install_dir/src"
cp "$repo_dir/requirements.txt" "$install_dir/requirements.txt"

python3 -m venv "$install_dir/.venv"
"$install_dir/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
    -r "$install_dir/requirements.txt"

cp "$repo_dir/packaging/macos/Info.plist" "$app_bundle/Contents/Info.plist"
cp "$repo_dir/packaging/macos/ai-usage-widget" "$app_bundle/Contents/MacOS/ai-usage-widget"
chmod +x "$app_bundle/Contents/MacOS/ai-usage-widget"

echo "Installed successfully: $app_bundle"
echo "Opening AI Usage Widget..."
open "$app_bundle"
