@echo off
setlocal
title OpenHands Nexus — First-Time Setup
set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;%USERPROFILE%\.cargo\bin;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\setup.ps1" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Setup finished with warnings or errors (Code: %ERRORLEVEL%).
)
pause
