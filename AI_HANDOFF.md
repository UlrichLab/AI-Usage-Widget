# AI Usage Widget — AI handoff protocol

Last updated: 2026-08-31  
Repository: https://github.com/UlrichLab/AI-Usage-Widget  
Branch: `main`  
Project version: `1.2.0`  
Last product commit before this handoff: `8db630c` (`Translate app interface to English`)

## Purpose of this document

This file gives a new AI assistant enough context to continue the project without
reconstructing the long preceding conversation. It summarizes the user's goals,
the implemented architecture, local installation state, important decisions,
known limitations, verification commands, and relevant history.

No access tokens, passwords, session cookies, private account addresses, or
signing-certificate identifiers are included here. Provider identities displayed
inside the local app must remain private and must not be committed.

## User's product goal

Maintain a compact cross-platform desktop application that shows remaining and
consumed AI usage for:

- Claude / Claude Code
- ChatGPT / Codex
- Cursor, including its separate usage pools and per-model breakdown

The ordinary Windows and macOS applications must work for non-developers after a
local source installation. The optional native macOS desktop widget is an extra
developer build and must not be required for the normal macOS app.

The user prefers:

- a compact dark interface;
- the same overall visual structure on Windows and macOS;
- provider limits ordered dynamically rather than hard-coded to one plan;
- consumed and remaining percentages together;
- full-width bars, including a completely filled bar at 100% remaining;
- larger, readable remaining-percentage labels;
- expandable account and Cursor-detail sections to avoid clutter;
- English UI labels across all app variants;
- no speculative reset times when a provider does not return one;
- Windows functionality to remain intact when macOS-specific code changes.

## Current platform variants

### Windows application

- Entry point: `src/ai_usage_widget.py`
- Installer: `install.ps1`
- Portable launcher: `start_ai_usage_widget.bat`
- Uninstaller: `uninstall.ps1`
- Runs as a normal Tkinter app with an `AI` system-tray icon.
- Python 3.10+ is required. The installer attempts to install Python through
  `winget` when it is missing.

### Normal macOS application — no Xcode required

- Entry point: `src/ai_usage_widget_macos.py`
- Installer command: `./scripts/macos/install.sh --app-only`
- Installed location: `~/Applications/AI Usage Widget.app`
- Built locally with PyInstaller.
- Requires macOS 14+, Python 3.10+, and Tkinter for the source build.
- Does not require Xcode, an Apple Developer membership, or a signing certificate.
- Contains all main usage views, account details, manual refresh, and the
  five-minute automatic refresh.

### macOS application plus WidgetKit desktop widget

- Widget view: `packaging/macos/widget/AIUsageWidget.swift`
- Host project: `packaging/macos/widget-host/AIUsageWidgetHost.xcodeproj`
- Installer command: `./scripts/macos/install.sh --with-widget`
- Requires full Xcode and a locally available Apple Development certificate.
- The installer derives bundle identifiers from the local development team, so
  another developer is not tied to the original user's signing identity.
- The extension reads sanitized usage snapshots from the local app on
  `http://127.0.0.1:38471/usage`.
- The local bridge exposes percentages and window metadata, not authentication
  tokens.
- The main AI Usage Widget app must remain running for guaranteed five-minute
  updates. WidgetKit can retain the last snapshot after the app exits, but it may
  then be stale.

## Shared architecture

- `src/usage_windows.py` normalizes provider responses into dynamic usage windows.
  It is shared by Windows and macOS and is the main place for labels, ordering,
  duration classification, and future provider-limit compatibility.
- `src/ai_usage_widget.py` contains the cross-platform/Windows UI and provider
  access used by the Windows app.
- `src/ai_usage_widget_macos.py` contains the macOS UI, Keychain/Claude Desktop
  integration, fallback behavior, and WidgetKit snapshot server.
- `packaging/macos/widget/AIUsageWidget.swift` renders the optional right-side
  macOS widget in small, medium, and large sizes.
- The app refresh interval is `300` seconds.
- Current app width is `450` pixels before dynamic height/layout calculations.

Whenever a shared visual or provider-window change is made, check all three UI
surfaces: Windows Python, macOS Python, and Swift WidgetKit.

## Provider behavior and data sources

### Claude

- Primary Claude Code path: existing Claude OAuth credentials. On macOS these can
  be read from Keychain; the Windows path supports the normal Claude credential
  location.
- Claude Desktop fallback exists on both Windows and macOS.
- On macOS, a cached Claude Desktop usage status can still be displayed after
  Claude Desktop closes. Old data is explicitly marked as saved/stale.
- Do not claim that a stale cached status is live.
- Claude limits are dynamic: session, weekly, model-specific, routines, Extra
  Usage, and newly introduced fields should be retained when recognizable.
- Extra Usage is important and shows consumed/remaining budget where returned.
- If Anthropic omits a reset timestamp, display `Reset: not reported by provider`.
  Do not invent or estimate a reset date.

### ChatGPT / Codex

- Reads the existing Codex authentication state from `~/.codex/auth.json` or the
  equivalent Windows user path.
- Uses the Codex/agent usage endpoint, not ordinary ChatGPT conversation usage.
- Labels are derived from provider durations, for example `5 hours`, `Weekly`, or
  `Monthly`.
- A seven-day reset is evidence for a weekly agent window; it is not a monthly
  ChatGPT subscription counter.
- Additional model-specific windows should remain dynamic.

### Cursor

- Reads Cursor's locally stored authenticated session and queries Cursor dashboard
  endpoints.
- Displays the separate `Cursor Models` and `Other Models` pools.
- Supports expandable model details and model-usage views.
- Per-model percentages describe shares of observed/weighted Cursor consumption;
  they are not separate monthly quotas.
- Cursor endpoints are not guaranteed stable public APIs and may require future
  maintenance if their response format changes.

## Account display and privacy

- The UI contains an expandable `Accounts` section for Claude, ChatGPT, and Cursor.
- It prefers a detected account email, then an account ID, then a generic signed-in
  or unavailable message.
- Account information is local UI state only.
- Never place real account addresses, OAuth tokens, JWTs, cookies, Keychain data,
  or Cursor database contents in source, fixtures, logs, screenshots, commits, or
  handoff documents.

## Current interface language

As of commit `8db630c`, visible labels in all three implementations are English.
Examples include:

- `used`, `remaining`, `free`
- `5 hours`, `Daily`, `Weekly`, `Monthly`
- `Reset: not reported by provider`
- `Saved status`
- `Accounts`
- `Model details` and `Model usage`
- `Show / Hide`, `Refresh now`, and `Quit`

Do not reintroduce German strings into one platform only unless localization is
implemented deliberately across every platform.

## macOS local state at handoff

- Validation machine: macOS `15.7.9` on Apple silicon.
- Xcode is installed and the developer WidgetKit build succeeds against the
  macOS 26.2 SDK.
- The current build is installed at:
  `~/Applications/AI Usage Widget.app`
- It was rebuilt with:

  ```bash
  ./scripts/macos/install.sh --with-widget
  ```

- The local snapshot endpoint was verified after installation. It returned
  English labels such as `5 hours` and `Weekly` for the active provider windows.
- The native widget may need WidgetKit/macOS to refresh its cached timeline after
  an update. The source app remains the authority for new snapshots.

## Repository and working-copy warning

The GitHub repository and its `main` branch are the source of truth.

At handoff time, `/Users/felay/Downloads/AI-Usage-Widget-main` is an extracted
mirror whose local `.git` directory has no commits. Do not use its Git history as
evidence and do not push from it without repairing/replacing that checkout.

Recommended start for another AI or account:

```bash
cd /path/to/a/safe/parent
git clone https://github.com/UlrichLab/AI-Usage-Widget.git
cd AI-Usage-Widget
git status
git log -5 --oneline
```

Preserve any user files before replacing an existing folder. Never delete or
reset a broad directory merely to obtain a clean clone.

## Verification commands

Run from a clean repository checkout:

```bash
python3 -m py_compile \
  src/ai_usage_widget.py \
  src/ai_usage_widget_macos.py \
  src/usage_windows.py

python3 -m unittest discover -s tests -v
git diff --check
```

At the handoff, all `28` unit tests passed.

For local macOS installation without the native desktop widget:

```bash
./scripts/macos/install.sh --app-only
```

For the developer WidgetKit build:

```bash
./scripts/macos/install.sh --with-widget
```

When the installed macOS app is running, the sanitized bridge can be checked with:

```bash
curl -fsS http://127.0.0.1:38471/usage
```

Do not publish the response if it contains information the user considers private.

## Important implementation history

The long conversation led to these milestones, in approximate order:

1. Diagnosed certificate and Python/Tkinter installation issues on macOS.
2. Converted the macOS build into a normal reopenable Dock application.
3. Added the optional WidgetKit desktop widget and Xcode signing workflow.
4. Clarified that the normal macOS app works without Xcode; only WidgetKit needs
   the developer toolchain.
5. Separated Windows, normal macOS, and macOS developer installation guides.
6. Added README previews for Windows, the macOS application, and the macOS widget.
7. Documented the five-minute refresh requirement and provider-app/login sources.
8. Expanded Claude, ChatGPT/Codex, and Cursor display to dynamic usage windows.
9. Added correct full-width behavior for 100%-remaining bars.
10. Added expandable account identities and compacted excess window space.
11. Enlarged percentage labels and aligned Windows styling with macOS.
12. Added Claude Desktop fallbacks on Windows and macOS, including an explicitly
    stale saved status when appropriate.
13. Fixed the macOS widget snapshot-loading path.
14. Replaced README preview images with the latest Windows and macOS screenshots.
15. Translated visible interface strings to English across Windows, normal macOS,
    and WidgetKit.

Recent relevant commits before this handoff:

```text
8db630c Translate app interface to English
9e2c294 Add offline Claude usage fallback on macOS
186bd00 Bust cached Windows preview image
a77c475 Refresh Windows preview image
ce9cea7 Fall back to Claude Desktop usage on Windows
8b6db3f Fix macOS widget snapshot loading
9365929 Update macOS app preview image
69b4f8b Align Windows app layout with macOS
1d1d16e Hide inactive internal Claude usage lanes
7905b2c Refresh Claude usage and enlarge percentage labels
8266fe9 Compact app window and hide idle scrollbar
0eb091c Add expandable provider account details
002f93f Fix usage bars at full width
75ce4ce Add dynamic provider usage windows
```

## README and public repository work already completed

- README has separate Windows and macOS step-by-step installation sections.
- It explains that the normal macOS app does not require Xcode.
- The optional right-side macOS widget is labeled as an Xcode developer-only view.
- The preview table keeps Windows on the left and the macOS application plus widget
  on the right.
- macOS 14 Sonoma, macOS 15 Sequoia, and macOS 26 Tahoe support is documented.
- Privacy, local-login requirements, provider reset behavior, and unstable Cursor
  endpoints are documented.
- The GitHub repository About/SEO topics and the user's public profile README were
  also improved during the broader session, including a link to
  https://ulrich-wiki.com/. Those profile settings are outside this repository and
  should be verified on GitHub rather than inferred from local files.

## Guardrails for the next AI

- Read this file and `README.md` before changing code.
- Inspect `git status` before edits; preserve unrelated user changes.
- Do not modify Windows behavior while implementing a macOS-only fix.
- Keep shared normalization in `src/usage_windows.py` where practical.
- If a UI term changes, update Windows Python, macOS Python, Swift WidgetKit, and
  affected tests together.
- Never fabricate usage percentages or reset timestamps.
- Distinguish live provider data from cached fallback data.
- Do not require Xcode for the ordinary macOS app.
- Do not commit build output, credentials, local databases, or signing material.
- Use `apply_patch` for source edits and run the full test suite afterward.
- For a local macOS deployment, rebuild and reinstall the app rather than editing
  files inside the installed `.app` bundle manually.

## Suggested first response from the next AI

The next assistant should confirm that it has read this handoff, state the current
repository commit it sees, run `git status`, and ask only for the user's next
desired change. It should not redo completed installation or UI work without new
evidence that it is broken.
