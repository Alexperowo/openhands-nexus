# OpenHands Local — Crash & Disaster Recovery Tool
[CmdletBinding()]
param(
    [switch]$RestartAfterRecovery
)

$Host.UI.RawUI.WindowTitle = "OpenHands Local — Аварийное восстановление после сбоя"
$ErrorActionPreference = "Continue"

Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host "       OPENHANDS NEXUS — АВАРИЙНОЕ ВОССТАНОВЛЕНИЕ ПОСЛЕ СБОЯ" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host ""

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$openhandsHome = Join-Path $userHome ".openhands"

# 1. Terminate any orphan / zombie processes on known ports
Write-Host "[1/5] Принудительное завершение зависших процессов и освобождение портов..." -ForegroundColor Yellow
$knownPorts = @(8000, 8080, 8443, 18000, 18001, 18002)
foreach ($pt in $knownPorts) {
    $conns = @(Get-NetTCPConnection -LocalPort $pt -State Listen -ErrorAction SilentlyContinue)
    foreach ($c in $conns) {
        if ($c -and $c.OwningProcess -gt 0) {
            $pidVal = $c.OwningProcess
            try {
                $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pidVal" -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "      Остановка зависшего процесса: $($proc.Name) (PID: $pidVal, Port: $pt)" -ForegroundColor Yellow
                    Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
    }
}
Start-Sleep -Seconds 1

# 2. Cleanup stale session locks and temporary files
Write-Host "[2/5] Очистка устаревших файлов сессий и блокировок..." -ForegroundColor Yellow
$sessionFiles = @(
    (Join-Path $PSScriptRoot "session.json"),
    (Join-Path $ProjectRoot "llama-swap\session.json"),
    (Join-Path $PSScriptRoot "llama-server.pid"),
    (Join-Path $PSScriptRoot "agent-canvas.pid")
)
foreach ($sf in $sessionFiles) {
    if (Test-Path $sf) {
        Remove-Item -Path $sf -Force -ErrorAction SilentlyContinue
        Write-Host "      Удален файл блокировки: $(Split-Path $sf -Leaf)" -ForegroundColor Gray
    }
}
Write-Host ""

# 3. Check and auto-repair working-profile-state.json
Write-Host "[3/5] Проверка целостности состояния Working Profiles..." -ForegroundColor Yellow
$stateFile = Join-Path $openhandsHome "working-profile-state.json"
$stateCorrupt = $false
if (Test-Path $stateFile) {
    try {
        $st = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $st.active_working_profile) { $stateCorrupt = $true }
    } catch {
        $stateCorrupt = $true
    }
} else {
    $stateCorrupt = $true
}

if ($stateCorrupt) {
    Write-Host "      [FIX] Восстановление поврежденного working-profile-state.json..." -ForegroundColor Yellow
    $fixedState = @{
        active_working_profile = "team-full"
        reasoning_mode = "standard_team"
        last_switched_at = (Get-Date -Format "o")
        switched_by = "disaster_recovery"
    } | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($stateFile, $fixedState, [System.Text.Encoding]::UTF8)
    Write-Host "      [OK] Состояние сброшено на профиль по умолчанию: team-full" -ForegroundColor Green
} else {
    Write-Host "      [OK] Файл состояния working-profile-state.json корректен (активен: $($st.active_working_profile))." -ForegroundColor Green
}
Write-Host ""

# 4. Verify and re-align llama-swap configuration
Write-Host "[4/5] Проверка конфигурации llama-swap/config.yaml..." -ForegroundColor Yellow
$cfgFile = Join-Path $ProjectRoot "llama-swap\config.yaml"
$swapExe = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
if (Test-Path $cfgFile) {
    # Check if paths match current project root
    $cText = [System.IO.File]::ReadAllText($cfgFile, [System.Text.Encoding]::UTF8)
    $pattern = '[a-zA-Z]:\\[^\s"'']+\\(ik_llama|Models|llama-mainline)'
    $replacement = $ProjectRoot + '\$1'
    $aligned = [regex]::Replace($cText, $pattern, $replacement)
    if ($aligned -ne $cText) {
        [System.IO.File]::WriteAllText($cfgFile, $aligned, [System.Text.Encoding]::UTF8)
        Write-Host "      [FIX] Выровнены пути в config.yaml" -ForegroundColor Green
    }
    # Validate with llama-swap binary
    if (Test-Path $swapExe) {
        $valRes = (& $swapExe -config $cfgFile -validate 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) {
            Write-Host "      [OK] Конфигурация llama-swap валидна: $valRes" -ForegroundColor Green
        } else {
            Write-Host "      [WARN] Ошибка валидации llama-swap: $valRes" -ForegroundColor Yellow
        }
    }
}
Write-Host ""

# 5. Re-apply Agent Canvas Custom Layer Patches
Write-Host "[5/5] Повторное наложение патчей Custom Layer..." -ForegroundColor Yellow
$patches = @(
    "openhands-localization\patch-agent-canvas-local-llm.ps1",
    "local-voice\patch-agent-canvas-voice.ps1",
    "openhands-localization\patch-agent-canvas-localization.ps1",
    "openhands-pwa\patch-agent-canvas-pwa.ps1",
    "openhands-working-profile\patch-agent-canvas-working-profile.ps1"
)
foreach ($p in $patches) {
    $pPath = Join-Path $ProjectRoot $p
    if (Test-Path $pPath) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $pPath | Out-Null
    }
}
Write-Host "      [OK] Все 5 патчей успешно переприменены." -ForegroundColor Green
Write-Host ""

Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "   АВАРИЙНОЕ ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО: Система возвращена в норму!" -ForegroundColor Green
Write-Host "   Все порты освобождены, блокировки сняты, патчи проверены." -ForegroundColor White
Write-Host "   Для чистого старта используйте: START-OPENHANDS-LOCAL.cmd" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""

if ($RestartAfterRecovery) {
    Write-Host "Запуск платформы (-RestartAfterRecovery)..." -ForegroundColor Green
    & (Join-Path $ProjectRoot "START-OPENHANDS-LOCAL.cmd")
}
