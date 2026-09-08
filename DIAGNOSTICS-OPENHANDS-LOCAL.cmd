@echo off
setlocal
title OpenHands Local - Diagnostics
set "PATH=C:\Program Files\nodejs;C:\Users\User\AppData\Roaming\npm;C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;C:\Users\User\.cargo\bin;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.openhands-local\diagnostics.ps1"