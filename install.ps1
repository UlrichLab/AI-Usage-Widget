$ErrorActionPreference = "Stop"

$AppName = "AI Usage Widget"
$InstallDir = Join-Path $env:LOCALAPPDATA "AIUsageWidget"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing $AppName 1.0.0..." -ForegroundColor Cyan

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            $v = & python --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $v -match "Python 3") { return "python" }
        } catch {}
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Python not found. Installing Python 3.13 with winget..." -ForegroundColor Yellow
        winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
        $Python = Find-Python
    }
}

if (-not $Python) {
    throw "Python 3.10+ is required. Install Python, reopen PowerShell, then run install.ps1 again."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $SourceDir "src") $InstallDir -Recurse -Force
Copy-Item (Join-Path $SourceDir "requirements.txt") $InstallDir -Force
Copy-Item (Join-Path $SourceDir "start_ai_usage_widget.bat") $InstallDir -Force

& $Python -m pip install --quiet --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")

$Shell = New-Object -ComObject WScript.Shell
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\AI Usage Widget.lnk"
$Shortcut = $Shell.CreateShortcut($StartMenu)
$Shortcut.TargetPath = Join-Path $InstallDir "start_ai_usage_widget.bat"
$Shortcut.WorkingDirectory = $InstallDir
$Icon = Join-Path $InstallDir "src\AI_Usage.ico"
if (Test-Path $Icon) { $Shortcut.IconLocation = $Icon }
$Shortcut.Save()

Write-Host ""
Write-Host "Installed successfully." -ForegroundColor Green
Write-Host "Start it from the Windows Start menu: AI Usage Widget"
Write-Host ""
Write-Host "The widget reads existing local logins for Claude Code, Codex/ChatGPT and Cursor."
