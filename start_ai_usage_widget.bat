@echo off
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PY_CMD=py"
if not defined PY_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo Python 3.10+ was not found.
  echo Run install.ps1 or install Python from https://www.python.org/
  pause
  exit /b 1
)

%PY_CMD% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" (
  start "" "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" "%~dp0src\ai_usage_widget.py"
) else (
  start "" /b %PY_CMD% "%~dp0src\ai_usage_widget.py"
)
endlocal
