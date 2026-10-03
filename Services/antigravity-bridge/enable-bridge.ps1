# Nexus Antigravity Bridge - Service Activator & Healthcheck
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "=== [Nexus Bridge] Активация моста рабочей станции ===" -ForegroundColor Cyan

$bridgeDir = $PSScriptRoot
$bridgeScript = Join-Path $bridgeDir "bridge.py"
$pythonw = "C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe"

if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    $pythonw = (Get-Command python.exe -ErrorAction Stop).Source
}

# 1. Установка CLOUD_CODE_URL
[System.Environment]::SetEnvironmentVariable("CLOUD_CODE_URL", "http://127.0.0.1:18005", "User")
$env:CLOUD_CODE_URL = "http://127.0.0.1:18005"
Write-Host "[1/3] CLOUD_CODE_URL установлен на http://127.0.0.1:18005 (HKCU\Environment)." -ForegroundColor Green

# 2. Проверка и запуск процесса
$conn = Get-NetTCPConnection -LocalPort 18005 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if (-not $conn) {
    Write-Host "[2/3] Запуск службы bridge.py в фоновом режиме..." -ForegroundColor Cyan
    Start-Process -FilePath $pythonw -ArgumentList "`"$bridgeScript`"" -WorkingDirectory $bridgeDir
    
    $attempts = 0
    while ($attempts -lt 10) {
        Start-Sleep -Milliseconds 400
        $conn = Get-NetTCPConnection -LocalPort 18005 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
        if ($conn) { break }
        $attempts++
    }
}

if ($conn) {
    Write-Host "[2/3] Служба моста активна (PID $($conn.OwningProcess)) на порту 18005." -ForegroundColor Green
} else {
    Write-Error "Не удалось запустить bridge.py на порту 18005. Проверьте bridge.log."
}

# 3. Healthcheck вызов
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:18005/v1internal:loadCodeAssist" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 5
    Write-Host "[3/3] Healthcheck успешен (Auth Vault: 200 OK)." -ForegroundColor Green
    Write-Host "`nNexus Bridge полностью готов к работе в Antigravity 2.0.`n" -ForegroundColor Green
} catch {
    Write-Warning "Healthcheck вернул предупреждение: $_"
}
