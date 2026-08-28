# Windows — step-by-step installation

This installs the Windows system-tray version. No Apple or macOS developer tools
are involved.

## Requirements

- Windows 10 or 11
- PowerShell
- Python 3.10 or newer

Python normally does not have to be installed manually. If it is missing, the
installer installs Python 3.13 automatically through Windows Package Manager
(`winget`). If `winget` is unavailable, install Python from
[python.org](https://www.python.org/downloads/windows/), reopen PowerShell, and
repeat the steps below.

## Installation

1. Download the repository with **Code > Download ZIP** and extract it, or clone
   the repository with Git.
2. Open the repository folder in File Explorer.
3. Right-click an empty area and select **Open in Terminal**. Make sure the
   terminal is using PowerShell.
4. Run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\install.ps1
   ```

5. Wait for the completion message.
6. Search for **AI Usage Widget** in the Windows Start menu and open it. The
   `AI` icon appears in the system tray.

The installer checks Python, installs the required packages, copies the app to
`%LOCALAPPDATA%\AIUsageWidget`, and creates the Start menu shortcut.

## Portable start

Alternatively, double-click `start_ai_usage_widget.bat` in the repository.
Python and the packages from the root `requirements.txt` must already be
installed for this method.
