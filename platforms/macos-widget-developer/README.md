# macOS app + WidgetKit desktop widget — developer build

This installs the normal macOS app and additionally embeds the WidgetKit view
shown in the macOS widget gallery.

Requirements:

- Full Xcode
- An Apple Account added under **Xcode > Settings > Accounts**
- An Apple Development certificate
- Python 3.10+ with Tkinter

Run from Terminal in the repository root:

```bash
brew install python@3.14 python-tk@3.14
chmod +x scripts/macos/install.sh
./scripts/macos/install.sh --with-widget
```

The command stops with a clear message when Xcode or the signing certificate is
missing; it does not silently replace the requested developer build with the
app-only version.
