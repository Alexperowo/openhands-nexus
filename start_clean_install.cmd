@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_clean_install.ps1"
if %errorlevel% neq 0 (
    echo [ERROR] Exit code: %errorlevel%
    pause
)