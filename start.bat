@echo off
rem Start the "add publication" desktop app.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Python environment not found. Run setup.bat first.
    pause
    exit /b 1
)

rem Make sure the local copy is current so the push does not conflict.
git pull --ff-only --quiet
if errorlevel 1 (
    echo.
    echo Warning: could not update the local copy from GitHub.
    echo The app will still open, but check your network or git state.
    echo.
    pause
)

start "" ".venv\Scripts\pythonw.exe" "tools\addpub_gui.pyw"
