# Platform installers

Choose the folder that matches the version you want to install:

| Folder | Version | Developer tools |
| --- | --- | --- |
| [`windows`](windows/README.md) | Windows system-tray app | Not required |
| [`macos-app`](macos-app/README.md) | Normal macOS Dock app with all usage views | Xcode not required |
| [`macos-widget-developer`](macos-widget-developer/README.md) | macOS app plus WidgetKit desktop widget | Full Xcode and an Apple Development certificate required |

The platform folders are installation guides. Shared application code remains
in `src/`, so Windows and macOS fixes do not need to be duplicated.
