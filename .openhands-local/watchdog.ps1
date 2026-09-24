<#
.SYNOPSIS
    OpenHands Nexus — Autonomous Watchdog & Self-Healing Supervisor
.DESCRIPTION
    Monitors all 5 microservices on Windows 11:
      1. llama-swap Model Router (Port 8080)
      2. Local Voice Bridge (Port 18002)
      3. Agent Canvas Web UI (Port 8000)
      4. OpenHands Core Engine (Port 18000)
      5. HTTPS LAN PWA Gateway (Port 8443)
    Detects unresponsiveness or crashes, terminates hung zombies,
    and automatically restarts individual services without disrupting the rest of the workstation.
#>

[CmdletBinding()]
param(
    [switch]$Background = $false,
    [switch]$Stop = $false,
    [switch]$Once = $false,
    [int]$IntervalSeconds = 5,
    [int]$FailureThreshold = 2
)

$ErrorActionPreference = "Continue"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidDir = $PSScriptRoot
$watchdogPidFile = Join-Path $pidDir "watchdog.pid"
$sessionFile = Join-Path $pidDir "session.json"
$diagLogDir = Join-Path $ProjectRoot "Logs\Diagnostics"
if (-not (Test-Path $diagLogDir)) { New-Item -ItemType Directory -Path $diagLogDir -Force | Out-Null }
$watchdogLog = Join-Path $diagLogDir "watchdog.log"

# Centralized Log Directories
$openhandsLogDir = Join-Path $ProjectRoot "Logs\OpenHands"
$swapLogDir = Join-Path $ProjectRoot "Logs\llama-swap"
$serverLogDir = Join-Path $ProjectRoot "Logs\llama-server"
$voiceLogDir = Join-Path $ProjectRoot "Logs\Voice"
$pwaLogDir = Join-Path $ProjectRoot "Logs\PWA"

function Log-Watchdog([string]$msg, [string]$color = "White") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [WATCHDOG] $msg"
    if (-not $Background) {
        Write-Host $line -ForegroundColor $color
    }
    Add-Content -Path $watchdogLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Rotate-WatchdogLog {
    if ((Test-Path $watchdogLog) -and (Get-Item $watchdogLog).Length -gt 5MB) {
        $oldLog = "$watchdogLog.1"
        Move-Item -Path $watchdogLog -Destination $oldLog -Force -ErrorAction SilentlyContinue
    }
}

# Handle -Stop command
if ($Stop) {
    if (Test-Path $watchdogPidFile) {
        $oldPid = Get-Content $watchdogPidFile -Raw -ErrorAction SilentlyContinue
        if ($oldPid -and $oldPid.Trim() -match '^\d+$') {
            $targetPid = [int]$oldPid.Trim()
            try {
                $p = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
                if ($p) {
                    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                    Write-Host "[WATCHDOG] Stopped running supervisor (PID: $targetPid)" -ForegroundColor Yellow
                }
            } catch {}
        }
        Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "[WATCHDOG] No active watchdog.pid found." -ForegroundColor Gray
    }
    exit 0
}

# Handle -Background delegation
if ($Background) {
    # Check if already running
    if (Test-Path $watchdogPidFile) {
        $existingPid = (Get-Content $watchdogPidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($existingPid -match '^\d+$') {
            $running = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
            if ($running) {
                Write-Host "[WATCHDOG] Watchdog is ALREADY running in background (PID: $existingPid)" -ForegroundColor Yellow
                exit 0
            }
        }
    }

    $procClass = [wmiclass]"Win32_Process"
    $startup = [wmiclass]"Win32_ProcessStartup"
    $startupInstance = $startup.CreateInstance()
    $startupInstance.ShowWindow = 0

    $scriptPath = $PSCommandPath
    $bgCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -IntervalSeconds $IntervalSeconds -FailureThreshold $FailureThreshold"
    $res = $procClass.Create($bgCmd, $ProjectRoot, $startupInstance)

    if ($res.ProcessId) {
        [System.IO.File]::WriteAllText($watchdogPidFile, "$($res.ProcessId)`n", [System.Text.UTF8Encoding]::new($false))
        Write-Host "[WATCHDOG] Started autonomous supervisor in background (PID: $($res.ProcessId))" -ForegroundColor Green
        Write-Host "           Logs: $watchdogLog" -ForegroundColor Gray
    } else {
        Write-Error "[WATCHDOG] Failed to spawn background supervisor process"
        exit 1
    }
    exit 0
}

# Record foreground/direct PID
[System.IO.File]::WriteAllText($watchdogPidFile, "$PID`n", [System.Text.UTF8Encoding]::new($false))

# WMI Classes for process operations
$procClass = [wmiclass]"Win32_Process"
$startup = [wmiclass]"Win32_ProcessStartup"
$startupInstance = $startup.CreateInstance()
$startupInstance.ShowWindow = 0

function Kill-PortProcess([int]$Port) {
    $conns = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($c in $conns) {
        if ($c -and $c.OwningProcess -gt 0) {
            $p = Get-CimInstance Win32_Process -Filter "ProcessId = $($c.OwningProcess)" -ErrorAction SilentlyContinue
            if ($p) {
                # Terminate children first
                $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($p.ProcessId)" -ErrorAction SilentlyContinue
                foreach ($chi in $children) {
                    try { Stop-Process -Id $chi.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
                }
                try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
    }
    Start-Sleep -Milliseconds 500
}

function Load-Session {
    if (Test-Path $sessionFile) {
        try {
            return Get-Content $sessionFile -Raw | ConvertFrom-Json
        } catch {}
    }
    return $null
}

function Save-SessionObject($sess) {
    if ($sess) {
        $json = $sess | ConvertTo-Json -Depth 5
        $tmp = "$sessionFile.tmp.$PID"
        [System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
        Move-Item -Path $tmp -Destination $sessionFile -Force -ErrorAction SilentlyContinue
    }
}

# Failure counters
$failCounts = @{
    "swap" = 0
    "voice" = 0
    "gateway" = 0
    "canvas" = 0
}

Log-Watchdog "=====================================================================" "Cyan"
Log-Watchdog "   OpenHands Nexus Autonomous Health Watchdog Started (PID: $PID)" "Cyan"
Log-Watchdog "   Polling interval: ${IntervalSeconds}s | Failure threshold: $FailureThreshold cycles" "Gray"
Log-Watchdog "=====================================================================" "Cyan"

try {
    while ($true) {
        Rotate-WatchdogLog

        # -------------------------------------------------------------
        # 1. Probe llama-swap Router (Port 8080)
        # -------------------------------------------------------------
        $swapHealthy = $false
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 -ErrorAction Stop
            if ($r -eq "OK") { $swapHealthy = $true }
        } catch {}

        if ($swapHealthy) {
            if ($failCounts["swap"] -gt 0) {
                Log-Watchdog "Service [llama-swap:8080] recovered and is now HEALTHY." "Green"
            }
            $failCounts["swap"] = 0
        } else {
            $failCounts["swap"]++
            Log-Watchdog "Service [llama-swap:8080] check failed ($($failCounts['swap'])/$FailureThreshold)" "Yellow"
            if ($failCounts["swap"] -ge $FailureThreshold) {
                Log-Watchdog "[SELF-HEAL] Restarting llama-swap router..." "Red"
                Kill-PortProcess -Port 8080
                
                $swapExe = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
                $swapConfig = Join-Path $ProjectRoot "llama-swap\config.yaml"
                $swapLog = Join-Path $swapLogDir "llama-swap.log"
                $swapCmd = "cmd.exe /c `"`"$swapExe`" -config `"$swapConfig`" -listen 127.0.0.1:8080 >> `"$swapLog`" 2>&1`""
                
                $res = $procClass.Create($swapCmd, $serverLogDir, $startupInstance)
                Start-Sleep -Seconds 2
                
                $c = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                $newPid = if ($c -and $c.OwningProcess -gt 0) { $c.OwningProcess } else { $res.ProcessId }
                
                $sess = Load-Session
                if ($sess) {
                    $sess.swap_owned = $true
                    $sess.swap_pid = $newPid
                    Save-SessionObject $sess
                }
                Log-Watchdog "[SELF-HEAL] llama-swap router relaunched (PID: $newPid)" "Green"
                $failCounts["swap"] = 0
            }
        }

        # -------------------------------------------------------------
        # 2. Probe Local Voice Bridge (Port 18002)
        # -------------------------------------------------------------
        $voiceHealthy = $false
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:18002/health" -TimeoutSec 2 -ErrorAction Stop
            if ($r -and $r.status -eq "ok") { $voiceHealthy = $true }
        } catch {}

        if ($voiceHealthy) {
            if ($failCounts["voice"] -gt 0) {
                Log-Watchdog "Service [Voice Bridge:18002] recovered and is now HEALTHY." "Green"
            }
            $failCounts["voice"] = 0
        } else {
            $failCounts["voice"]++
            Log-Watchdog "Service [Voice Bridge:18002] check failed ($($failCounts['voice'])/$FailureThreshold)" "Yellow"
            if ($failCounts["voice"] -ge $FailureThreshold) {
                Log-Watchdog "[SELF-HEAL] Restarting Local Voice Bridge..." "Red"
                Kill-PortProcess -Port 18002

                $pythonwCmd = Get-Command "pythonw.exe" -ErrorAction SilentlyContinue
                $pythonwExe = if ($pythonwCmd) { $pythonwCmd.Source } else { "pythonw.exe" }
                $voiceScript = Join-Path $ProjectRoot "local-voice\service.py"
                $voiceCmd = "`"$pythonwExe`" `"$voiceScript`" 18002"

                $res = $procClass.Create($voiceCmd, $ProjectRoot, $startupInstance)
                Start-Sleep -Seconds 2

                $c = Get-NetTCPConnection -LocalPort 18002 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                $newPid = if ($c -and $c.OwningProcess -gt 0) { $c.OwningProcess } else { $res.ProcessId }

                $sess = Load-Session
                if ($sess) {
                    $sess.voice_owned = $true
                    $sess.voice_pid = $newPid
                    Save-SessionObject $sess
                }
                Log-Watchdog "[SELF-HEAL] Voice Bridge relaunched (PID: $newPid)" "Green"
                $failCounts["voice"] = 0
            }
        }

        # -------------------------------------------------------------
        # 3. Probe Mobile LAN PWA Gateway (Port 8443)
        # -------------------------------------------------------------
        $gatewayHealthy = $false
        $conn8443 = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn8443) { $gatewayHealthy = $true }

        if ($gatewayHealthy) {
            if ($failCounts["gateway"] -gt 0) {
                Log-Watchdog "Service [LAN Gateway:8443] recovered and is now HEALTHY." "Green"
            }
            $failCounts["gateway"] = 0
        } else {
            $failCounts["gateway"]++
            Log-Watchdog "Service [LAN Gateway:8443] check failed ($($failCounts['gateway'])/$FailureThreshold)" "Yellow"
            if ($failCounts["gateway"] -ge $FailureThreshold) {
                Log-Watchdog "[SELF-HEAL] Restarting Mobile LAN PWA Gateway..." "Red"
                Kill-PortProcess -Port 8443

                $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
                if (-not $nodeExe) { $nodeExe = "C:\Program Files\nodejs\node.exe" }
                $gwScript = Join-Path $ProjectRoot "openhands-pwa\lan-gateway.mjs"
                $pwaLog = Join-Path $pwaLogDir "lan-gateway.log"
                $gwCmd = "cmd.exe /c `"`"$nodeExe`" `"$gwScript`" >> `"$pwaLog`" 2>&1`""

                $res = $procClass.Create($gwCmd, (Join-Path $ProjectRoot "openhands-pwa"), $startupInstance)
                Start-Sleep -Seconds 2

                $c = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                $newPid = if ($c -and $c.OwningProcess -gt 0) { $c.OwningProcess } else { $res.ProcessId }

                $sess = Load-Session
                if ($sess) {
                    $sess.gateway_owned = $true
                    $sess.gateway_pid = $newPid
                    Save-SessionObject $sess
                }
                Log-Watchdog "[SELF-HEAL] LAN Gateway relaunched (PID: $newPid)" "Green"
                $failCounts["gateway"] = 0
            }
        }

        # -------------------------------------------------------------
        # 4. Probe Agent Canvas Web UI (Port 8000) & Core (Port 18000)
        # -------------------------------------------------------------
        $canvasHealthy = $false
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $canvasHealthy = $true }
        } catch {}

        if ($canvasHealthy) {
            if ($failCounts["canvas"] -gt 0) {
                Log-Watchdog "Service [Agent Canvas:8000] recovered and is now HEALTHY." "Green"
            }
            $failCounts["canvas"] = 0
        } else {
            $failCounts["canvas"]++
            Log-Watchdog "Service [Agent Canvas:8000] check failed ($($failCounts['canvas'])/$FailureThreshold)" "Yellow"
            if ($failCounts["canvas"] -ge $FailureThreshold) {
                Log-Watchdog "[SELF-HEAL] Restarting Agent Canvas and Core..." "Red"
                Kill-PortProcess -Port 8000
                Kill-PortProcess -Port 3001
                Kill-PortProcess -Port 18000
                Kill-PortProcess -Port 18001

                # Clean up any lingering zombie node/cmd processes
                $lingering = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                    ($_.CommandLine -like "*agent-canvas*" -or $_.CommandLine -like "*static-server.mjs*") -and
                    ($_.Name -in @('node.exe', 'cmd.exe', 'agent-canvas.exe'))
                }
                foreach ($proc in $lingering) {
                    try {
                        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($proc.ProcessId)" -ErrorAction SilentlyContinue
                        foreach ($chi in $children) { try { Stop-Process -Id $chi.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }
                        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                    } catch {}
                }

                $canvasLog = Join-Path $openhandsLogDir "agent-canvas.log"
                $canvasCmd = "cmd.exe /c `"set \""INGRESS_HOST=127.0.0.1\"" && set \""PATH=C:\Program Files\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;%USERPROFILE%\.cargo\bin;%PATH%\"" && agent-canvas.cmd >> `"$canvasLog`" 2>&1`""

                $res = $procClass.Create($canvasCmd, $ProjectRoot, $startupInstance)
                Start-Sleep -Seconds 5

                $sess = Load-Session
                if ($sess -and $res.ProcessId) {
                    $sess.canvas_owned = $true
                    $sess.canvas_pids = @($res.ProcessId)
                    Save-SessionObject $sess
                }
                Log-Watchdog "[SELF-HEAL] Agent Canvas relaunched" "Green"
                $failCounts["canvas"] = 0
            }
        }

        if ($Once) {
            break
        }

        Start-Sleep -Seconds $IntervalSeconds
    }
} finally {
    if (Test-Path $watchdogPidFile) {
        $curPid = Get-Content $watchdogPidFile -Raw -ErrorAction SilentlyContinue
        if ($curPid -and $curPid.Trim() -eq "$PID") {
            Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
        }
    }
    Log-Watchdog "Watchdog supervisor exited." "Gray"
}
