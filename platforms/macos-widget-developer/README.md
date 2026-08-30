# macOS app + WidgetKit desktop widget — developer-only build

This installs the normal macOS app and additionally embeds the WidgetKit view
shown in the macOS widget gallery.

Requirements:

- Full Xcode
- An Apple Account added under **Xcode > Settings > Accounts**
- An Apple Development certificate
- Python 3.10+ with Tkinter

Complete the following steps:

1. Download and extract or clone the repository.
2. Add your Apple Account under **Xcode > Settings > Accounts** and create an
   **Apple Development** certificate.
3. Open Terminal in the repository root.
4. Run:

   ```bash
   brew install python@3.14 python-tk@3.14
   chmod +x scripts/macos/install.sh
   ./scripts/macos/install.sh --with-widget
   ```

5. Open macOS **Edit Widgets**, search for **AI Usage**, and add the small,
   medium, or large widget. Small summarizes each provider; medium and large
   display the additional time and model-specific limits.

The command stops with a clear message when Xcode or the signing certificate is
missing; it does not silently replace the requested developer build with the
app-only version.
