@echo off
setlocal
title RESTART OpenHands Local
set "PATH=C:\Program Files\nodejs;C:\Users\User\AppData\Roaming\npm;C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;C:\Users\User\.cargo\bin;%PATH%"

echo =====================================================================
echo                RESTARTING OPENHANDS LOCAL PLATFORM
echo =====================================================================
echo.

call "%~dp0STOP-OPENHANDS-LOCAL.cmd"
ping -n 4 127.0.0.1 >nul
call "%~dp0START-OPENHANDS-LOCAL.cmd"

if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%