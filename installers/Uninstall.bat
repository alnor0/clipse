@echo off
rem Clipse uninstaller for Windows - double-click it.
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "APP=%USERPROFILE%\.clipse\app"
set "BIN=%USERPROFILE%\.local\bin"
set "CLIENT="
if exist "%BIN%\clipse.exe" set "CLIENT=%BIN%\clipse.exe"
if exist "%APP%\Scripts\clipse.exe" set "CLIENT=%APP%\Scripts\clipse.exe"
if defined CLIENT (
    "%CLIENT%" --no-autostart >nul 2>nul
    "%CLIENT%" --stop >nul 2>nul
    timeout /t 2 /nobreak >nul
    "%CLIENT%" --uninstall-resolve-shortcuts
)
if exist "%APP%" rmdir /s /q "%APP%"
del /q "%BIN%\clipse.exe" "%BIN%\clipse-daemon.exe" >nul 2>nul
rem a copy an older version installed with pipx
set "PIPX_DEFAULT_BACKEND=pip"
for %%v in (3.14 3.13 3.12 3.11 3.10 3.9) do py -%%v-64 -m pipx uninstall davinci-search >nul 2>nul
echo Clipse is removed.
set /p A=Also delete your Clipse settings and favourites? [y/N] 
if /i "%A%"=="y" (
  rmdir /s /q "%USERPROFILE%\.clipse" 2>nul
  rmdir /s /q "%APPDATA%\Clipse" 2>nul
  rmdir /s /q "%LOCALAPPDATA%\Clipse" 2>nul
  echo Settings deleted.
)
echo Done.
pause
