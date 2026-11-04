@echo off
rem One-time setup on a new PC:  git clone ... ,  then run this file once.
rem Installs Git / Python if missing (via winget), creates .venv, installs packages,
rem and makes sure git knows your name and e-mail for commits.
setlocal
cd /d "%~dp0"
set NEEDS_RERUN=0

echo [1/5] Checking Git...
where git >nul 2>&1
if errorlevel 1 (
    echo   Git not found. Installing with winget...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    set NEEDS_RERUN=1
) else (
    for /f "tokens=*" %%v in ('git --version') do echo   %%v
)

echo [2/5] Checking Python...
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY ( python --version >nul 2>&1 && set PY=python )
if not defined PY (
    echo   Python not found. Installing with winget...
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    set NEEDS_RERUN=1
) else (
    for /f "tokens=*" %%v in ('%PY% --version') do echo   %%v
)

if "%NEEDS_RERUN%"=="1" (
    echo.
    echo Git and/or Python were just installed. Close this window and run setup.bat again.
    pause
    exit /b 0
)

echo [3/5] Creating the Python environment (.venv)...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo   Failed to create .venv
        pause
        exit /b 1
    )
)

echo [4/5] Installing packages...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r tools\requirements.txt
if errorlevel 1 (
    echo   pip install failed. Check your network connection.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo   Warning: tkinter is missing. Reinstall Python with the "tcl/tk" option enabled.
)

echo [5/5] Checking git identity...
for /f "tokens=*" %%n in ('git config user.name') do set GIT_NAME=%%n
for /f "tokens=*" %%e in ('git config user.email') do set GIT_EMAIL=%%e
if not defined GIT_NAME call :ask_name
if not defined GIT_EMAIL call :ask_email
echo   %GIT_NAME% / %GIT_EMAIL%

echo.
echo Setup complete. Run start.bat to open the app.
echo (On the first push, Git may open a browser window to sign in to GitHub.)
if /i not "%~1"=="/nopause" pause
endlocal
exit /b 0

:ask_name
set /p GIT_NAME=  Your name for commits, e.g. hiro-yamamu:
git config --global user.name "%GIT_NAME%"
exit /b 0

:ask_email
set /p GIT_EMAIL=  Your e-mail for commits, GitHub noreply address recommended:
git config --global user.email "%GIT_EMAIL%"
exit /b 0
