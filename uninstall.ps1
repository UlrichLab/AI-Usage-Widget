$InstallDir = Join-Path $env:LOCALAPPDATA "AIUsageWidget"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\AI Usage Widget.lnk"

Get-Process -Name pythonw,python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path -match "Python" } |
    ForEach-Object { }

if (Test-Path $StartMenu) { Remove-Item $StartMenu -Force }
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }

Write-Host "AI Usage Widget removed." -ForegroundColor Green
