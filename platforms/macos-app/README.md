# macOS app — no Xcode required

This installs the normal Dock application with the Claude, ChatGPT/Codex, and
Cursor views. Only the optional desktop WidgetKit view is omitted.

Run from Terminal in the repository root:

```bash
brew install python@3.14 python-tk@3.14
chmod +x scripts/macos/install.sh
./scripts/macos/install.sh --app-only
```

If Homebrew is unavailable, install a current Python package with Tkinter from
[python.org](https://www.python.org/downloads/macos/) before running the final
two commands.
