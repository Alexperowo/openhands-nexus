# Nexus Antigravity Bridge - Emergency Disable & Cloud Passthrough
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "=== [Nexus Bridge] Отключение моста (Emergency Disable) ===" -ForegroundColor Yellow

# 1. Сброс переменной среды CLOUD_CODE_URL
[System.Environment]::SetEnvironmentVariable("CLOUD_CODE_URL", $null, "User")
$env:CLOUD_CODE_URL = $null
Write-Host "[1/3] Переменная CLOUD_CODE_URL удалена из реестра пользователя (HKCU\Environment)." -ForegroundColor Green

# 2. Остановка службы на порту 18005
$conn = Get-NetTCPConnection -LocalPort 18005 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if ($conn) {
    $pidToKill = $conn.OwningProcess
    try {
        $proc = Get-Process -Id $pidToKill -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[2/3] Остановка процесса моста PID $pidToKill ($($proc.ProcessName))..." -ForegroundColor Cyan
            Stop-Process -Id $pidToKill -Force
            Start-Sleep -Milliseconds 500
        }
    } catch {
        Write-Warning "Не удалось корректно остановить PID $pidToKill: $_"
    }
} else {
    Write-Host "[2/3] Порт 18005 уже свободен." -ForegroundColor Gray
}

# 3. Финальная проверка
$activeConn = Get-NetTCPConnection -LocalPort 18005 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if (-not $activeConn) {
    Write-Host "[3/3] Мост полностью отключён. Google Antigravity переходит на прямое облачное подключение." -ForegroundColor Green
    Write-Host "`nДля вступления в силу в открытых окнах Antigravity может потребоваться перезапуск приложения.`n" -ForegroundColor Yellow
} else {
    Write-Error "Внимание: порт 18005 всё ещё занят процессом PID $($activeConn.OwningProcess)!"
}
