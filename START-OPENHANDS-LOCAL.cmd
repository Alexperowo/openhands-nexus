@echo off
setlocal
title START OpenHands Local
set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;%USERPROFILE%\.cargo\bin;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\start.ps1"
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Startup failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
ping 127.0.0.1 -n 6 >nul