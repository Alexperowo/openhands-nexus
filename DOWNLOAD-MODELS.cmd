@echo off
setlocal
title OpenHands Nexus — Download AI Models
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\download-models.ps1" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Model download finished with warnings or errors (Code: %ERRORLEVEL%).
)
pause
