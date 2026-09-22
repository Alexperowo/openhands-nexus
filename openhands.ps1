<#
.SYNOPSIS
    OpenHands Nexus — Unified Station CLI Manager
.DESCRIPTION
    Consolidated CLI entry point for orchestrating, testing, and managing
    all OpenHands Nexus services on Windows 11.
#>

[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'watch', 'watchdog', 'vram', 'check', 'test', 'setup', 'diagnose', 'recover', 'backup', 'restore', 'update', 'help')]
    [string]$Command = 'help',

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot

function Show-Help {
    Write-Host ''
    Write-Host '=====================================================================' -ForegroundColor Cyan
    Write-Host '         OpenHands Nexus — Unified Station CLI (v1.0)' -ForegroundColor Cyan
    Write-Host '=====================================================================' -ForegroundColor Cyan
    Write-Host 'Использование:'
    Write-Host '  openhands start       - Запустить все сервисы (Llama-swap, Voice, Core, Canvas, PWA)' -ForegroundColor White
    Write-Host '  openhands stop        - Остановить все сервисы станции' -ForegroundColor White
    Write-Host '  openhands restart     - Полный перезапуск сервисов платформы' -ForegroundColor White
    Write-Host '  openhands status      - Проверить активность портов, процессов, VRAM и LLM' -ForegroundColor White
    Write-Host '  openhands watch       - Запустить автономный наблюдатель и самовосстановление [-Background]' -ForegroundColor White
    Write-Host '  openhands vram        - Проверить распределение памяти GPU (NVML)' -ForegroundColor White
    Write-Host '  openhands check       - Запустить 34 теста зависимостей и целостности' -ForegroundColor White
    Write-Host '  openhands test        - Запустить автоматизированные тесты (--all, --unit, --integration, --hardware)' -ForegroundColor White
    Write-Host '  openhands diagnose    - Запустить детальную диагностику станции' -ForegroundColor White
    Write-Host '  openhands recover     - Запустить процедуру аварийного восстановления' -ForegroundColor White
    Write-Host '  openhands backup      - Создать резервную копию рабочей станции' -ForegroundColor White
    Write-Host '  openhands restore     - Восстановить станцию из последней копии' -ForegroundColor White
    Write-Host '  openhands update      - Проверить/обновить компоненты станции (Canvas, Swap, Voice, PWA, LLM)' -ForegroundColor White
    Write-Host '  openhands setup       - Первичная инициализация и установка зависимостей' -ForegroundColor White
    Write-Host '=====================================================================' -ForegroundColor Cyan
    Write-Host ''
}

function Get-StationStatus {
    Write-Host ''
    Write-Host '[STATUS] Проверка сетевых сервисов OpenHands Nexus...' -ForegroundColor Cyan
    $ports = @(
        @{
            Port = 18000; Name = 'OpenHands Core Engine' 
        },
        @{
            Port = 8000;  Name = 'Agent Canvas Web UI' 
        },
        @{
            Port = 8080;  Name = 'llama-swap Model Router' 
        },
        @{
            Port = 8443;  Name = 'HTTPS LAN PWA Gateway' 
        },
        @{
            Port = 18002; Name = 'Local Voice Bridge (GigaAM)' 
        }
    )

    $allActive = $true
    foreach ($p in $ports) {
        $conn = Get-NetTCPConnection -LocalPort $p.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            Write-Host "  [ACTIVE]   Port $($p.Port): $($p.Name) (PID: $($conn.OwningProcess))" -ForegroundColor Green
        } else {
            Write-Host "  [INACTIVE] Port $($p.Port): $($p.Name)" -ForegroundColor Yellow
            $allActive = $false
        }
    }

    Write-Host ''
    # Watchdog status
    $watchPidFile = Join-Path $Root ".openhands-local\watchdog.pid"
    $watchRunning = $false
    $watchPid = $null
    if (Test-Path $watchPidFile) {
        $wPid = (Get-Content $watchPidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($wPid -match '^\d+$') {
            $wp = Get-Process -Id ([int]$wPid) -ErrorAction SilentlyContinue
            if ($wp) { $watchRunning = $true; $watchPid = $wPid }
        }
    }
    if ($watchRunning) {
        Write-Host "  [ACTIVE]   Autonomous Watchdog Supervisor (PID: $watchPid)" -ForegroundColor Green
    } else {
        Write-Host "  [STANDBY]  Autonomous Watchdog (не активен, запуск: openhands watch -Background)" -ForegroundColor DarkGray
    }

    # Active LLM Model inspection
    try {
        $mRes = Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/models" -TimeoutSec 2 -ErrorAction Stop
        if ($mRes -and $mRes.data) {
            $loaded = ($mRes.data | Where-Object { $_.status.value -eq "loaded" }).id
            if ($loaded) {
                Write-Host "  [ACTIVE]   LLM Model: $loaded (загружена в VRAM)" -ForegroundColor Green
            } else {
                Write-Host "  [STANDBY]  LLM Model: выгружена (on-demand standby)" -ForegroundColor Cyan
            }
        }
    } catch {}

    Write-Host ''
    if ($allActive) {
        Write-Host '  Все 5 сервисов активны и готовы к работе.' -ForegroundColor Green
        Write-Host '  Desktop: http://127.0.0.1:8000' -ForegroundColor Cyan
        $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker' } |
                  Sort-Object InterfaceMetric |
                  Select-Object -First 1).IPAddress
        if ($lanIp) {
            Write-Host "  Mobile:  https://${lanIp}:8443" -ForegroundColor Cyan
        }
    } else {
        Write-Host '  Один или более сервисов не запущены. Запустите: openhands start' -ForegroundColor Yellow
    }

    # VRAM status summary
    try {
        $vramJson = python "$Root\Config\vram_manager.py" --json 2>$null
        if ($vramJson) {
            $vramData = $vramJson | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($vramData -and $vramData.gpus) {
                Write-Host ''
                Write-Host '  Распределение VRAM (Dual-GPU Pool):' -ForegroundColor DarkCyan
                foreach ($g in $vramData.gpus) {
                    Write-Host "    GPU $($g.index): $($g.name) -> $($g.used_mb) / $($g.total_mb) MiB (Свободно: $($g.free_mb) MiB)" -ForegroundColor DarkGray
                }
            }
        }
    } catch {}
    Write-Host ''
}

function Invoke-StationScript([string]$scriptPath, [string[]]$scriptArgs) {
    if (-not (Test-Path $scriptPath)) {
        Write-Error "[CLI Error] Скрипт не найден: $scriptPath"
        exit 1
    }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath @scriptArgs
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } catch {
        Write-Error "[CLI Error] Ошибка выполнения $scriptPath : $_"
        exit 1
    }
}

switch ($Command) {
    'start' {
        Invoke-StationScript "$Root\.openhands-local\start.ps1" $RemainingArgs
    }
    'stop' {
        Invoke-StationScript "$Root\.openhands-local\watchdog.ps1" @("-Stop")
        Invoke-StationScript "$Root\.openhands-local\stop.ps1" $RemainingArgs
    }
    'restart' {
        Write-Host '[CLI] Перезапуск OpenHands Nexus...' -ForegroundColor Cyan
        Invoke-StationScript "$Root\.openhands-local\watchdog.ps1" @("-Stop")
        Invoke-StationScript "$Root\.openhands-local\stop.ps1" @()
        Start-Sleep -Seconds 3
        Invoke-StationScript "$Root\.openhands-local\start.ps1" @()
    }
    'status' {
        Get-StationStatus
    }
    'watch' {
        Invoke-StationScript "$Root\.openhands-local\watchdog.ps1" $RemainingArgs
    }
    'watchdog' {
        Invoke-StationScript "$Root\.openhands-local\watchdog.ps1" $RemainingArgs
    }
    'vram' {
        python "$Root\Config\vram_manager.py" @RemainingArgs
    }
    'check' {
        Invoke-StationScript "$Root\.openhands-local\check-dependencies.ps1" $RemainingArgs
    }
    'test' {
        python "$Root\Tests\runner.py" @RemainingArgs
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    'diagnose' {
        Invoke-StationScript "$Root\.openhands-local\diagnostics.ps1" $RemainingArgs
    }
    'recover' {
        Invoke-StationScript "$Root\.openhands-local\recover.ps1" $RemainingArgs
    }
    'setup' {
        Invoke-StationScript "$Root\.openhands-local\setup.ps1" $RemainingArgs
    }
    'backup' {
        Invoke-StationScript "$Root\OpenHands-Update\scripts\backup-station.ps1" $RemainingArgs
    }
    'restore' {
        Invoke-StationScript "$Root\OpenHands-Update\scripts\restore-station.ps1" $RemainingArgs
    }
    'update' {
        $updateArgs = @()
        if ($RemainingArgs.Count -gt 0) {
            $firstArg = $RemainingArgs[0]
            if ($firstArg -notlike "-*") {
                $updateArgs += @("-Component", $firstArg)
                if ($RemainingArgs.Count -gt 1) {
                    $updateArgs += $RemainingArgs[1..($RemainingArgs.Count - 1)]
                }
            } else {
                $updateArgs = $RemainingArgs
            }
        }
        Invoke-StationScript "$Root\OpenHands-Update\scripts\update-all.ps1" $updateArgs
    }
    default {
        Show-Help
    }
}
