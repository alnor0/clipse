@echo off
rem Clipse installer for Windows - double-click it.
rem Installs into its own folder (%USERPROFILE%\.clipse\app) using
rem Python from python.org. Nothing else on the PC is changed.
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
rem run straight from the project folder, not the download
if not exist pyproject.toml cd ..
set "APP=%USERPROFILE%\.clipse\app"
set "BIN=%USERPROFILE%\.local\bin"
echo == Installing Clipse ==
echo.

rem Find a 64-bit Python 3.9 or newer (Resolve's scripting library is 64-bit)
set "PYV="
for %%v in (3.14 3.13 3.12 3.11 3.10 3.9) do (
    if not defined PYV (
        py -%%v-64 -c "import sys" >nul 2>nul && set "PYV=%%v"
    )
)
if not defined PYV (
    echo Installing Python 3.12...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --override "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1"
    if errorlevel 1 (
        echo.
        echo Couldn't install Python automatically. Install the 64-bit Python 3.12 from
        echo https://www.python.org/downloads/windows/ - then double-click Install.bat again.
        pause
        exit /b 1
    )
    echo.
    echo Python is installed. Close this window and double-click Install.bat again.
    pause
    exit /b 0
)
set "PY=py -%PYV%-64"
echo Using Python %PYV%

rem Stop a running copy first - Windows can't replace files that are in use
rem (--shutdown also stops the login helper; versions before 1.31 only know --stop)
for %%c in ("%BIN%\clipse.exe" "%APP%\Scripts\clipse.exe") do (
    if exist %%c ( %%c --shutdown >nul 2>nul || %%c --stop >nul 2>nul )
)
timeout /t 2 /nobreak >nul
rem Remove a copy an older version installed with pipx
set "PIPX_DEFAULT_BACKEND=pip"
%PY% -m pipx uninstall davinci-search >nul 2>nul

echo Installing the app (the first time downloads about 140 MB - give it a minute)...
%PY% -m venv --clear "%APP%" || goto :fail
set "APPPY=%APP%\Scripts\python.exe"
"%APPPY%" -m pip install --quiet --disable-pip-version-check --upgrade pip >nul 2>nul
"%APPPY%" -m pip install --quiet --disable-pip-version-check . || goto :fail
rem Previewing sounds and clips (optional - only from ready-made builds)
for %%e in (miniaudio av numpy) do (
    "%APPPY%" -m pip install --quiet --disable-pip-version-check --only-binary=:all: %%e >nul 2>nul || echo   ^(couldn't add %%e - previews or sound analysis may be missing, everything else works^)
)

if not exist "%BIN%" mkdir "%BIN%"
copy /y "%APP%\Scripts\clipse.exe" "%BIN%\" >nul
copy /y "%APP%\Scripts\clipse-daemon.exe" "%BIN%\" >nul
"%APP%\Scripts\clipse.exe" --install-resolve-shortcuts || goto :fail
rem Start in the background at login, so the first open is instant (Settings -^> General)
"%APP%\Scripts\clipse.exe" --autostart

echo.
echo Done! Next: restart DaVinci Resolve and give the shortcuts keys in
echo DaVinci Resolve -^> Keyboard Customization (search for "Clipse").
pause
exit /b 0

:fail
echo.
echo Something went wrong - see the messages above.
pause
exit /b 1
