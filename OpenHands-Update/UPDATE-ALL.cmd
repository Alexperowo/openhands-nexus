@echo off
setlocal
cd /d "K:\Project\OpenHands-Update"
if "%~1"=="" (
    echo [INFO] No arguments specified. Defaulting safely to -CheckOnly mode.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-all.ps1" -CheckOnly
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-all.ps1" %*
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Process failed with error level %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
pause
