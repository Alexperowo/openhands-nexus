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
    [ValidateSet('start', 'stop', 'restart', 'status', 'check', 'test', 'setup', 'diagnose', 'recover', 'backup', 'restore', 'help')]
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
    Write-Host '  openhands status      - Проверить активность портов и процессов' -ForegroundColor White
    Write-Host '  openhands check       - Запустить 34 теста зависимостей и целостности' -ForegroundColor White
    Write-Host '  openhands test        - Запустить автоматизированные тесты (--all, --unit, --integration, --hardware)' -ForegroundColor White
    Write-Host '  openhands diagnose    - Запустить детальную диагностику станции' -ForegroundColor White
    Write-Host '  openhands recover     - Запустить процедуру аварийного восстановления' -ForegroundColor White
    Write-Host '  openhands backup      - Создать резервную копию рабочей станции' -ForegroundColor White
    Write-Host '  openhands restore     - Восстановить станцию из последней копии' -ForegroundColor White
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
    if ($allActive) {
        Write-Host '  Все 5 сервисов активны и готовы к работе.' -ForegroundColor Green
        Write-Host '  Desktop: http://127.0.0.1:8000' -ForegroundColor Cyan
        $lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1).IPAddress
        if ($lanIp) {
            Write-Host "  Mobile:  https://${lanIp}:8443" -ForegroundColor Cyan
        }
    } else {
        Write-Host '  Один или более сервисов не запущены. Запустите: openhands start' -ForegroundColor Yellow
    }
    Write-Host ''
}

function Invoke-StationScript([string]$scriptPath, [string[]]$scriptArgs) {
    if (-not (Test-Path $scriptPath)) {
        Write-Error "[CLI Error] Скрипт не найден: $scriptPath"
        exit 1
    }
    try {
        & $scriptPath @scriptArgs
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
        Invoke-StationScript "$Root\.openhands-local\stop.ps1" $RemainingArgs
    }
    'restart' {
        Write-Host '[CLI] Перезапуск OpenHands Nexus...' -ForegroundColor Cyan
        Invoke-StationScript "$Root\.openhands-local\stop.ps1" @()
        Start-Sleep -Seconds 3
        Invoke-StationScript "$Root\.openhands-local\start.ps1" @()
    }
    'status' {
        Get-StationStatus
    }
    'check' {
        Invoke-StationScript "$Root\.openhands-local\check-dependencies.ps1" $RemainingArgs
    }
    'test' {
        python "$Root\tests\runner.py" @RemainingArgs
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
    default {
        Show-Help
    }
}
