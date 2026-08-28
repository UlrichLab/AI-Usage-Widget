# AI Usage Widget

![Windows version](https://img.shields.io/badge/Windows-1.0.0-blue)
![macOS version](https://img.shields.io/badge/macOS-1.1.4-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

A compact Windows system-tray app and native macOS app with a WidgetKit desktop widget for monitoring AI subscription and agent usage across:

- **Claude / Claude Code**
- **ChatGPT / Codex**
- **Cursor**
- **Cursor per-model usage breakdown**

The Windows app lives in the system tray. On macOS, the app behaves like a normal Dock application and can supply an optional desktop widget.

## Preview

<table>
  <tr>
    <th>Windows</th>
    <th>macOS</th>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <img src="assets/ai-usage-widget-preview.png" alt="AI Usage Widget on Windows" width="100%">
    </td>
    <td width="50%" align="center" valign="top">
      <img src="assets/ai-usage-widget-macos-app.jpg" alt="AI Usage Widget app on macOS" width="100%"><br><br>
      <strong>Widget</strong><br>
      <img src="assets/ai-usage-widget-macos-widget.jpg" alt="AI Usage desktop widget on macOS" width="100%">
    </td>
  </tr>
</table>

## Features

- Remaining and consumed usage shown together
- Reset countdown and reset date when the provider exposes it
- Claude Extra Usage support
- ChatGPT / Codex weekly or 5-hour agent limit support
- Separate Cursor **Cursor Models** and **Other Models** pools
- Expandable Cursor model table with requests, weighted usage and costs
- Expandable **Model consumption** view with one bar per Cursor model
- `AI` system-tray icon on Windows
- Native Dock application and WidgetKit widget on macOS
- Manual refresh and 5-minute auto-refresh
- Optional always-on-top mode
- No API keys need to be pasted into the app

## Platform support

- **Windows 10/11:** stable
- **macOS 14 Sonoma, macOS 15 Sequoia, and macOS 26 Tahoe:** native app bundle and WidgetKit extension built locally by the installer

The established Windows entry point remains unchanged. macOS has a separate native build entry point so its Dock, WidgetKit, Keychain, and Claude Desktop integrations do not change Windows behavior.

## Installation

### Windows

#### Recommended

Download or clone the repository, then open PowerShell in the repository folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The installer:

1. detects Python,
2. can install Python through `winget` when Python is missing,
3. installs the small Python dependencies,
4. copies the app to `%LOCALAPPDATA%\AIUsageWidget`,
5. creates an **AI Usage Widget** Start Menu shortcut.

After installation, search for **AI Usage Widget** in the Windows Start menu.

#### Portable start

You can also run the repository copy directly:

```text
start_ai_usage_widget.bat
```

### macOS

Clone or download the repository, open Terminal in the repository folder, and run:

```bash
chmod +x scripts/macos/install.sh
./scripts/macos/install.sh
```

Before installation, install full Xcode, sign in under **Xcode > Settings > Accounts**, and create an **Apple Development** certificate.

The installer:

1. checks for Python 3.10+, Tkinter, full Xcode, and a signing certificate,
2. creates an isolated build environment inside the repository,
3. builds a self-contained native macOS application with its own Dock icon,
4. builds and embeds the signed WidgetKit extension,
5. creates `~/Applications/AI Usage Widget.app`, registers it with macOS, and opens it.

The **AI Usage** widget can then be added from macOS **Edit Widgets** in small
or medium size. The desktop app must be running for fresh usage data; WidgetKit
keeps the most recent timeline entry between refreshes.

AI Usage Widget refreshes once at launch and then automatically every five
minutes while the app remains open. If the app is closed, the desktop widget can
continue showing its last timeline entry, but that value is no longer guaranteed
to be current.

Closing the macOS app window quits the app. Launch it again from Finder,
Spotlight, Launchpad, or the Dock. Use macOS **Keep in Dock** if you want its
icon to remain there while the app is closed.

If Tkinter is missing, install Python from [python.org](https://www.python.org/downloads/macos/) or install the matching `python-tk` package through Homebrew.

## Data sources and required provider apps

AI Usage Widget does not create separate provider logins. A supported local app
or CLI must already be installed and signed in for each status you want to see:

| Status | Required local login |
| --- | --- |
| **Claude** | Claude Desktop or Claude Code. With Claude Desktop only, open Claude periodically so its local usage cache stays current. |
| **ChatGPT** | Codex desktop app or Codex CLI, which supplies `~/.codex/auth.json`. The ChatGPT desktop app by itself does not supply this Codex quota login. |
| **Cursor** | Cursor Desktop, signed in to the account whose usage should be displayed. |

The provider apps do not all need to remain open continuously. The **AI Usage
Widget app itself must remain running** for the desktop widget to receive a new
snapshot every five minutes.

## macOS compatibility

The macOS build has a deployment target of macOS 14.0 and uses APIs available on
Sonoma, Sequoia, and Tahoe. The installer builds natively for the Mac on which it
is run and derives unique host and widget bundle identifiers from that user's
Apple Development Team, so a public clone does not depend on the repository
owner's signing identity.

The current source has been validated on macOS 15.7.9 with Xcode 26.3, compiled
successfully against the macOS 26.2 Tahoe SDK, and is tested by CI on both macOS
and Windows. Full Xcode and a local Apple Development certificate are still
required because the public repository does not ship a pre-signed, notarized
binary.

## Requirements

- Windows 10/11 or macOS 14+
- Python 3.10+
- Full Xcode and an Apple Development certificate for the macOS WidgetKit build
- A supported, signed-in local provider app or CLI as listed above

### Claude

On macOS, the app first uses the existing Claude Code OAuth credentials from the
macOS Keychain. If Claude Code is not installed, it can fall back to the current,
non-sensitive usage cache written by the signed-in Claude Desktop app.

Typical location:

```text
%USERPROFILE%\.claude\.credentials.json
```

Claude Desktop-only users should open Claude Desktop periodically so its local
usage cache remains current. The app can show normal 5h/7d limits when exposed
by Anthropic. For accounts using **Extra Usage**, it displays used and remaining
budget. When Anthropic does not expose a reset timestamp, the widget says that
the provider did not report one instead of estimating a date.

### ChatGPT / Codex

The app reads the existing Codex login:

```text
%USERPROFILE%\.codex\auth.json
```

The displayed quota is the Codex / agent quota associated with the ChatGPT account. Normal ChatGPT conversations are not necessarily part of this quota.

### Cursor

The app reads Cursor's locally stored authenticated session and queries the Cursor dashboard endpoints.

It displays two separate pools:

- **Cursor Models**
- **Other Models**

It can additionally show an expandable per-model breakdown with:

- model name
- requests
- weighted Cursor usage
- observed costs

## About Cursor model percentages

The **Model consumption** percentages are the share of the model usage captured in the queried Cursor usage events. They are **not separate monthly limits for each model**.

For example:

```text
GPT model A      41% share
Claude model B   28% share
Gemini model C   17% share
```

means model A accounts for approximately 41% of the captured weighted usage.

## Privacy

AI Usage Widget does not ask you to paste API keys into the UI.

It reads the local authentication state already created by the installed provider tools and queries their usage endpoints. The macOS desktop-widget bridge exposes only usage percentages on `127.0.0.1`; it does not expose authentication tokens.

No telemetry is intentionally collected by this project.

## Important compatibility note

Some provider endpoints used for usage data—especially Cursor dashboard endpoints—are not stable public APIs. Providers can change them without notice.

If an upstream service changes its response format, a future widget update may be required.

## Uninstall

### Windows

From the cloned/downloaded repository:

```powershell
.\uninstall.ps1
```

### macOS

From the cloned/downloaded repository:

```bash
chmod +x scripts/macos/uninstall.sh
./scripts/macos/uninstall.sh
```

## Version

- Windows: **1.0.0**
- macOS: **1.1.4**

## License

MIT
