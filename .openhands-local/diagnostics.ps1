# OpenHands Local Diagnostics Script
$Host.UI.RawUI.WindowTitle = "OpenHands Local — Диагностика"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "               OPENHANDS LOCAL — ДИАГНОСТИКА СИСТЕМЫ" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $ProjectRoot "Logs"
$sessionFile = Join-Path $PSScriptRoot "session.json"

# 1. Check Session State
Write-Host "[1/4] Состояние сессии (session.json):" -ForegroundColor Yellow
if (Test-Path $sessionFile) {
    try {
        $sess = Get-Content $sessionFile -Raw | ConvertFrom-Json
        Write-Host "  llama_owned:  $($sess.llama_owned) (PID: $($sess.llama_pid))" -ForegroundColor Gray
        Write-Host "  voice_owned:  $($sess.voice_owned) (PID: $($sess.voice_pid))" -ForegroundColor Gray
        Write-Host "  canvas_owned: $($sess.canvas_owned) (PIDs: $($sess.canvas_pids -join ', '))" -ForegroundColor Gray
    } catch {
        Write-Host "  Ошибка чтения session.json" -ForegroundColor Red
    }
} else {
    Write-Host "  session.json не найден (система не была запущена лаунчером)" -ForegroundColor Gray
}
Write-Host ""

# 2. Check Ports
Write-Host "[2/4] Статус сетевых портов:" -ForegroundColor Yellow
$ports = @(
    @{ Port = 8443; Service = "OpenHands Nexus Gateway (HTTPS)" },
    @{ Port = 8080; Service = "Local LLM Router (llama-swap)" },
    @{ Port = 18000; Service = "OpenHands Agent Server" },
    @{ Port = 18002; Service = "Local Voice Bridge & Working Profiles API" }
)

foreach ($item in $ports) {
    $p = $item.Port
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pName = (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Write-Host "  Порт $p [$($item.Service)]: " -NoNewline -ForegroundColor White
        Write-Host "СЛУШАЕТ " -NoNewline -ForegroundColor Green
        Write-Host "(PID $($conn.OwningProcess) - $pName)" -ForegroundColor Cyan
    } else {
        Write-Host "  Порт $p [$($item.Service)]: " -NoNewline -ForegroundColor White
        Write-Host "НЕ АКТИВЕН" -ForegroundColor Red
    }
}
Write-Host ""

# 3. Health Checks
Write-Host "[3/4] Проверка работоспособности сервисов (Health Check):" -ForegroundColor Yellow

# LLM Health
try {
    $m = Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/models" -TimeoutSec 2 -ErrorAction Stop
    $modelId = $m.data[0].id
    Write-Host "  LLM Backend (8080):      " -NoNewline -ForegroundColor White
    Write-Host "OK " -NoNewline -ForegroundColor Green
    Write-Host "(Модель: $([System.IO.Path]::GetFileName($modelId)))" -ForegroundColor Gray
} catch {
    Write-Host "  LLM Backend (8080):      " -NoNewline -ForegroundColor White
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}

# Voice Health
try {
    $v = Invoke-RestMethod -Uri "http://127.0.0.1:18002/health" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  Voice Bridge (18002):    " -NoNewline -ForegroundColor White
    Write-Host "OK " -NoNewline -ForegroundColor Green
    Write-Host "(STT: $($v.stt_engine) | TTS: $($v.tts_engine) | RAM: $($v.ram_mb) MB)" -ForegroundColor Gray
} catch {
    Write-Host "  Voice Bridge (18002):    " -NoNewline -ForegroundColor White
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}

# Agent Server Health
try {
    $c = Invoke-WebRequest -Uri "http://localhost:18000" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "  Agent Server (18000):    " -NoNewline -ForegroundColor White
    Write-Host "OK " -NoNewline -ForegroundColor Green
    Write-Host "(HTTP статус: $($c.StatusCode))" -ForegroundColor Gray
} catch {
    Write-Host "  Agent Server (18000):    " -NoNewline -ForegroundColor White
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# 4. Recent Log Lines
Write-Host "[4/4] Последние строки журналов (logs):" -ForegroundColor Yellow
$logTargets = @(
    @{ Name = "OpenHands Agent Canvas"; Path = Join-Path $ProjectRoot "Logs\OpenHands\agent-canvas.log" },
    @{ Name = "OpenHands Launcher"; Path = Join-Path $ProjectRoot "Logs\OpenHands\launcher.log" },
    @{ Name = "llama-swap Router"; Path = Join-Path $ProjectRoot "Logs\llama-swap\llama-swap.log" },
    @{ Name = "llama-server Engine"; Path = Join-Path $ProjectRoot "Logs\llama-server\llama.log" },
    @{ Name = "Local Voice Bridge"; Path = Join-Path $ProjectRoot "Logs\Voice\voice-bridge.log" }
)
foreach ($lt in $logTargets) {
    Write-Host "  --- $($lt.Name) ---" -ForegroundColor Cyan
    if (Test-Path $lt.Path) {
        $lines = Get-Content $lt.Path -Tail 4 -ErrorAction SilentlyContinue
        if ($lines) {
            foreach ($line in $lines) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "    (файл пуст)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "    (файл лога пока не создан)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
if ([Environment]::UserInteractive -and -not $env:NONINTERACTIVE) {
    Write-Host "Действия: [1] Открыть UI  [2] Открыть папку логов  [Enter] Выход" -ForegroundColor White
    $choice = Read-Host "Выберите действие"
    if ($choice -eq "1") {
        Start-Process "https://localhost:8443"
    } elseif ($choice -eq "2") {
        Start-Process "explorer.exe" $logDir
    }
}