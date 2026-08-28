# macOS app — step-by-step installation without Xcode

This installs the normal Dock application with the Claude, ChatGPT, and Cursor
views. The only feature not included is the optional WidgetKit desktop widget.

## Requirements

- macOS 14 or newer
- Terminal
- Python 3.10 or newer with Tkinter

## Installation

1. Download the repository with **Code > Download ZIP** and extract it, or clone
   the repository with Git.
2. Open Terminal, type `cd ` including the trailing space, drag the repository
   folder into Terminal, and press Return.
3. Install Python and Tkinter through Homebrew:

   ```bash
   brew install python@3.14 python-tk@3.14
   ```

   If Homebrew is unavailable, install a current Python package with Tkinter
   from [python.org](https://www.python.org/downloads/macos/) and skip this step.

4. Build and install the app:

   ```bash
   chmod +x scripts/macos/install.sh
   ./scripts/macos/install.sh --app-only
   ```

5. The finished app is installed in `~/Applications`, registered with macOS,
   and opened automatically. Reopen it later through Finder, Spotlight,
   Launchpad, or the Dock.

The app refreshes once at launch and then every five minutes while it remains
open. Xcode and an Apple Developer membership are not required for this version.
