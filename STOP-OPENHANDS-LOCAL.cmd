@echo off
setlocal
title STOP OpenHands Local
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\stop.ps1"
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Shutdown failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
ping 127.0.0.1 -n 4 >nul