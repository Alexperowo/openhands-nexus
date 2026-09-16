@echo off
setlocal
title OpenHands Nexus — Complete Automated Installer
set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;C:\Program Files\Git\cmd;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%USERPROFILE%\.cargo\bin;%PATH%"

echo =====================================================================
echo           OPENHANDS NEXUS - AUTOMATED WINDOWS 11 INSTALLER
echo =====================================================================
echo.
echo Installing system prerequisites, Python libraries, Agent Canvas,
echo and configuring OpenHands Nexus overlay...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\install-prerequisites.ps1" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Installation completed with warnings or errors (Code: %ERRORLEVEL%).
)
pause
