@echo off
setlocal
set PATH=C:\Program Files\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;%USERPROFILE%\.cargo\bin;%PATH%
powershell -NoProfile -ExecutionPolicy Bypass -File %~dp0openhands.ps1 %*
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
