@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\rollback-openhands.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Rollback failed with error level %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
pause
