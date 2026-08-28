# AI Usage Widget

**Version 1.0.0**

A compact Windows system-tray widget for monitoring AI subscription and agent usage across:

- **Claude / Claude Code**
- **ChatGPT / Codex**
- **Cursor**
- **Cursor per-model usage breakdown**

The widget is designed to stay out of the way: it lives in the Windows system tray and opens on demand.

## Features

- Remaining and consumed usage shown together
- Reset countdown and reset date when the provider exposes it
- Claude Extra Usage support
- ChatGPT / Codex weekly or 5-hour agent limit support
- Separate Cursor **Cursor Models** and **Other Models** pools
- Expandable Cursor model table with requests, weighted usage and costs
- Expandable **Model consumption** view with one bar per Cursor model
- `AI` system-tray icon
- Manual refresh and 5-minute auto-refresh
- Optional always-on-top mode
- No API keys need to be pasted into the app

## Windows installation

### Recommended

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

### Portable start

You can also run the repository copy directly:

```text
start_ai_usage_widget.bat
```

## Requirements

- Windows 10 or Windows 11
- Python 3.10+
- For each provider you want to monitor, its corresponding local app/CLI must already be logged in.

### Claude

The app uses the existing Claude Code OAuth credentials stored by Claude Code.

Typical location:

```text
%USERPROFILE%\.claude\.credentials.json
```

It can show normal 5h/7d limits when exposed by Anthropic. For accounts using **Extra Usage**, it displays used/remaining budget. Some Extra Usage account types do not expose a reset timestamp; in that case the widget explicitly says that the reset is not reported.

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

It reads the local authentication state already created by the installed provider tools and queries their usage endpoints.

No telemetry is intentionally collected by this project.

## Important compatibility note

Some provider endpoints used for usage data—especially Cursor dashboard endpoints—are not stable public APIs. Providers can change them without notice.

If an upstream service changes its response format, a future widget update may be required.

## Uninstall

From the cloned/downloaded repository:

```powershell
.\uninstall.ps1
```

## Version

Current release: **1.0.0**

## License

MIT
