#!/bin/sh

set -eu

install_dir="$HOME/Library/Application Support/AIUsageWidget"
app_bundle="$HOME/Applications/AI Usage Widget.app"

rm -rf "$install_dir" "$app_bundle"
echo "AI Usage Widget removed."
