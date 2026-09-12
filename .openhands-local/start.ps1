# OpenHands Local Startup Script (Background / Hidden Mode via WMI)
$ErrorActionPreference = "Continue"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$localAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }

$env:PATH = "C:\Program Files\nodejs;" + (Join-Path $appData "npm") + ";" + (Join-Path $localAppData "Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools") + ";" + (Join-Path $env:USERPROFILE ".cargo\bin") + ";" + $env:PATH
$pidDir = $PSScriptRoot
if (-not (Test-Path $pidDir)) { New-Item -ItemType Directory -Path $pidDir | Out-Null }
$sessionFile = Join-Path $pidDir "session.json"
# Canonical Centralized Logs Hierarchy
$canonicalLogs = Join-Path $ProjectRoot "Logs"
$openhandsLogDir = Join-Path $canonicalLogs "OpenHands"
$swapLogDir = Join-Path $canonicalLogs "llama-swap"
$serverLogDir = Join-Path $canonicalLogs "llama-server"
$voiceLogDir = Join-Path $canonicalLogs "Voice"
$diagLogDir = Join-Path $canonicalLogs "Diagnostics"
$pwaLogDir = Join-Path $canonicalLogs "PWA"

foreach ($d in @($openhandsLogDir, $swapLogDir, $serverLogDir, $voiceLogDir, $diagLogDir, $pwaLogDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

$launcherLog = Join-Path $openhandsLogDir "launcher.log"

function Log-Message([string]$msg, [string]$color = "White") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $msg -ForegroundColor $color
    Add-Content -Path $launcherLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Rotate-LogFile([string]$logPath, [int]$maxGenerations = 5) {
    if (-not (Test-Path $logPath)) { return }
    $oldest = "$logPath.$maxGenerations"
    if (Test-Path $oldest) {
        Remove-Item -Path $oldest -Force -ErrorAction SilentlyContinue
    }
    for ($i = $maxGenerations - 1; $i -ge 1; $i--) {
        $curr = "$logPath.$i"
        $next = "$logPath." + ($i + 1)
        if (Test-Path $curr) {
            Move-Item -Path $curr -Destination $next -Force -ErrorAction SilentlyContinue
        }
    }
    $legacyOld = "$logPath.old"
    if (Test-Path $legacyOld) {
        if (-not (Test-Path "$logPath.1")) {
            Move-Item -Path $legacyOld -Destination "$logPath.1" -Force -ErrorAction SilentlyContinue
        } else {
            Remove-Item -Path $legacyOld -Force -ErrorAction SilentlyContinue
        }
    }
    Move-Item -Path $logPath -Destination "$logPath.1" -Force -ErrorAction SilentlyContinue
}

Rotate-LogFile $launcherLog

function Wait-ForServiceReady {
    param(
        [string]$Url = $null,
        [int]$Port = 0,
        [int]$TimeoutSeconds = 30,
        [scriptblock]$Validator = $null
    )
    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        Start-Sleep -Seconds 1
        try {
            if ($Url) {
                $res = Invoke-RestMethod -Uri $Url -TimeoutSec 2 -ErrorAction Stop
                if ($Validator) {
                    if (& $Validator $res) { return $true }
                } elseif ($res) {
                    return $true
                }
            } elseif ($Port -gt 0) {
                $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($conn) { return $true }
            }
        } catch {}
    }
    return $false
}

Log-Message "=====================================================================" "Cyan"
Log-Message "               STARTING OPENHANDS LOCAL PLATFORM" "Cyan"
Log-Message "=====================================================================" "Cyan"
Log-Message ""

# WMI Hidden Process Startup Configuration (SW_HIDE = 0)
$procClass = [wmiclass]"Win32_Process"
$startup = [wmiclass]"Win32_ProcessStartup"
$startupInstance = $startup.CreateInstance()
$startupInstance.ShowWindow = 0

# Load existing session if any, or initialize
$session = @{
    swap_owned = $false
    swap_pid = $null
    llama_owned = $false
    llama_pid = $null
    canvas_owned = $false
    canvas_pids = @()
    voice_owned = $false
    voice_pid = $null
    gateway_owned = $false
    gateway_pid = $null
}
if (Test-Path $sessionFile) {
    try {
        $loaded = Get-Content $sessionFile -Raw | ConvertFrom-Json
        if ($loaded) {
            $session.swap_owned = [bool]$loaded.swap_owned
            $session.swap_pid = $loaded.swap_pid
            $session.llama_owned = [bool]$loaded.llama_owned
            $session.llama_pid = $loaded.llama_pid
            $session.canvas_owned = [bool]$loaded.canvas_owned
            if ($loaded.canvas_pids) { $session.canvas_pids = @($loaded.canvas_pids) }
            $session.voice_owned = [bool]$loaded.voice_owned
            $session.voice_pid = $loaded.voice_pid
            $session.gateway_owned = [bool]$loaded.gateway_owned
            $session.gateway_pid = $loaded.gateway_pid
        }
    } catch {}
}

function Save-Session {
    $sessionJson = $session | ConvertTo-Json -Depth 5
    $tmpSession = "$sessionFile.tmp.$PID"
    [System.IO.File]::WriteAllText($tmpSession, $sessionJson, [System.Text.UTF8Encoding]::new($false))
    Move-Item -Path $tmpSession -Destination $sessionFile -Force
}

$swapRunning = $false

# 1. Check if llama-swap is already running on port 8080
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 -ErrorAction Stop
    if ($res -eq "OK") {
        Log-Message "[OK] llama-swap router is ALREADY running on port 8080" "Green"
        Log-Message "     Reusing existing llama-swap instance." "Gray"
        $swapRunning = $true
        if (-not $session.swap_owned) {
            $session.swap_owned = $false
            $session.swap_pid = $null
            Log-Message "     [OWNERSHIP] swap_owned = false (pre-existing instance, will NOT be stopped by STOP launcher)" "DarkGray"
        } else {
            Log-Message "     [OWNERSHIP] swap_owned = true (managed by this session)" "DarkGray"
        }
    }
} catch {
    $conn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Log-Message "[ERROR] Port 8080 is occupied by an unrecognized service (PID: $($conn.OwningProcess))." "Red"
        Log-Message "        Aborting launch to prevent conflicts." "Yellow"
        exit 1
    }
}

if (-not $swapRunning) {
    Log-Message "[1/3] Starting llama-swap router in background (port 8080, Qwen & Ornith on-demand)..." "Cyan"
    
    $env:GGML_CUDA_NO_PINNED = "1"
    $swapLog = Join-Path $swapLogDir "llama-swap.log"
    Rotate-LogFile $swapLog

    $swapExe = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
    $swapConfig = Join-Path $ProjectRoot "llama-swap\config.yaml"
    $swapCmd = "cmd.exe /c `"`"$swapExe`" -config `"$swapConfig`" -listen 127.0.0.1:8080 > `"$swapLog`" 2>&1`""

    # Use llama-server log dir as cwd so any default llama.log drops into canonical Logs\llama-server\
    $wmiRes = $procClass.Create($swapCmd, $serverLogDir, $startupInstance)

    $ready = Wait-ForServiceReady -Url "http://127.0.0.1:8080/health" -TimeoutSeconds 30 -Validator { param($r) $r -eq "OK" }

    if ($ready) {
        $c8080 = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        $actualSwapPid = if ($c8080 -and $c8080.OwningProcess -gt 0) { $c8080.OwningProcess } else { $wmiRes.ProcessId }
        $session.swap_owned = $true
        $session.swap_pid = $actualSwapPid
        Save-Session
        Log-Message "[OK] llama-swap router online in background (PID: $actualSwapPid)" "Green"
        Log-Message "     [OWNERSHIP] swap_owned = true (launched by this session)" "DarkGray"
    } else {
        Log-Message "[ERROR] llama-swap failed to respond in 30s. Check $swapLog" "Red"
        exit 1
    }
}

Log-Message ""

# Ensure UI patches are active in Agent Canvas build (Local LLM, Voice, Russian Localization, PWA & Working Profile)
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-localization\patch-agent-canvas-local-llm.ps1") | Out-Null
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "local-voice\patch-agent-canvas-voice.ps1") | Out-Null
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-localization\patch-agent-canvas-localization.ps1") | Out-Null
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-pwa\patch-agent-canvas-pwa.ps1") | Out-Null
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-working-profile\patch-agent-canvas-working-profile.ps1") | Out-Null
} catch {
    Log-Message "[WARN] UI patch error: $_" "Yellow"
}

$voiceRunning = $false
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:18002/health" -TimeoutSec 2 -ErrorAction Stop
    if ($res -and $res.status -eq "ok") {
        Log-Message "[OK] Local Voice Bridge is ALREADY running at http://127.0.0.1:18002" "Green"
        Log-Message "     Reusing existing Voice Bridge instance." "Gray"
        $voiceRunning = $true
        if (-not $session.voice_owned) {
            $session.voice_owned = $false
            $session.voice_pid = $null
            Log-Message "     [OWNERSHIP] voice_owned = false (pre-existing instance, will NOT be stopped by STOP launcher)" "DarkGray"
        } else {
            Log-Message "     [OWNERSHIP] voice_owned = true (managed by this session)" "DarkGray"
        }
    }
} catch {}

if (-not $voiceRunning) {
    Log-Message "[2/3] Starting Local Voice Bridge in background (GigaAM v3 STT + Supertonic 3 TTS)..." "Cyan"

    $voiceLog = Join-Path $voiceLogDir "voice-bridge.log"
    Rotate-LogFile $voiceLog

    $pythonwCmd = Get-Command "pythonw.exe" -ErrorAction SilentlyContinue
    $pythonwExe = if ($pythonwCmd) { $pythonwCmd.Source } else { "pythonw.exe" }
    $voiceScript = Join-Path $ProjectRoot "local-voice\service.py"
    $voiceCmd = "`"$pythonwExe`" `"$voiceScript`" 18002"

    $wmiVoiceRes = $procClass.Create($voiceCmd, $ProjectRoot, $startupInstance)

    $vReady = Wait-ForServiceReady -Url "http://127.0.0.1:18002/health" -TimeoutSeconds 30 -Validator { param($r) $r -and $r.status -eq "ok" }

    if ($vReady) {
        $c18002 = Get-NetTCPConnection -LocalPort 18002 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        $actualVoicePid = if ($c18002 -and $c18002.OwningProcess -gt 0) { $c18002.OwningProcess } else { $wmiVoiceRes.ProcessId }
        $session.voice_owned = $true
        $session.voice_pid = $actualVoicePid
        Save-Session
        Log-Message "[OK] Local Voice Bridge online in background (PID: $actualVoicePid)" "Green"
        Log-Message "     [OWNERSHIP] voice_owned = true (launched by this session)" "DarkGray"
    } else {
        Log-Message "[WARN] Local Voice Bridge did not respond on 18002 within 30s. Check $voiceLog" "Yellow"
    }
}

Log-Message ""

# 3. Check if Agent Canvas is already running on port 8000
$canvasRunning = $false
try {
    $res = Invoke-WebRequest -Uri "http://127.0.0.1:8000" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    if ($res.StatusCode -eq 200) {
        Log-Message "[OK] OpenHands Agent Canvas is ALREADY running at http://127.0.0.1:8000" "Green"
        Log-Message "     Opening existing UI in browser (no duplicate started)..." "Gray"
        $canvasRunning = $true
        if (-not $session.canvas_owned) {
            $session.canvas_owned = $false
            $session.canvas_pids = @()
            Log-Message "     [OWNERSHIP] canvas_owned = false (pre-existing instance, will NOT be stopped by STOP launcher)" "DarkGray"
        } else {
            Log-Message "     [OWNERSHIP] canvas_owned = true (managed by this session)" "DarkGray"
        }
        Start-Process "http://127.0.0.1:8000"
    }
} catch {
    $conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Log-Message "[ERROR] Port 8000 is occupied by an unrecognized service (PID: $($conn.OwningProcess))." "Red"
        Log-Message "        Aborting launch to prevent conflicts." "Yellow"
        exit 1
    }
}

if (-not $canvasRunning) {
    Log-Message "[3/3] Starting OpenHands Agent Canvas in background..." "Cyan"

    $canvasLog = Join-Path $openhandsLogDir "agent-canvas.log"
    Rotate-LogFile $canvasLog

    $canvasCmd = "cmd.exe /c `"set \""INGRESS_HOST=127.0.0.1\"" && set \""PATH=C:\Program Files\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools;%USERPROFILE%\.cargo\bin;%PATH%\"" && agent-canvas.cmd >> `"$canvasLog`" 2>&1`""
    $wmiCanvasRes = $procClass.Create($canvasCmd, $ProjectRoot, $startupInstance)
    if ($wmiCanvasRes.ProcessId) {
        $session.canvas_owned = $true
        $session.canvas_pids = @($wmiCanvasRes.ProcessId)
        Save-Session
    }

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $async = $tcp.BeginConnect("127.0.0.1", 8000, $null, $null)
            $tcpOk = $async.AsyncWaitHandle.WaitOne(500)
            $tcp.Close()
            if ($tcpOk) {
                $res = Invoke-WebRequest -Uri "http://127.0.0.1:8000" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
                if ($res -and $res.StatusCode -eq 200) {
                    $ready = $true
                    break
                }
            }
        } catch {}
    }

    if ($ready) {
        # Wait briefly for backend services on 18000/18001 to finish binding so their PIDs are captured
        for ($w = 0; $w -lt 5; $w++) {
            $p18 = Get-NetTCPConnection -LocalPort 18001 -State Listen -ErrorAction SilentlyContinue
            if ($p18) { break }
            Start-Sleep -Seconds 1
        }
        $savedPids = @()
        if ($wmiCanvasRes.ProcessId) {
            $savedPids += $wmiCanvasRes.ProcessId
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($wmiCanvasRes.ProcessId)" -ErrorAction SilentlyContinue
            foreach ($c in $children) {
                $savedPids += $c.ProcessId
                $grand = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($c.ProcessId)" -ErrorAction SilentlyContinue
                foreach ($g in $grand) {
                    $savedPids += $g.ProcessId
                    $greatGrand = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($g.ProcessId)" -ErrorAction SilentlyContinue
                    foreach ($gg in $greatGrand) { $savedPids += $gg.ProcessId }
                }
            }
        }

        # Also capture all child processes of listening node/python processes on ports 8000, 18000, 18001
        $portList = @(8000, 18000, 18001)
        foreach ($pt in $portList) {
            $conns = @(Get-NetTCPConnection -LocalPort $pt -State Listen -ErrorAction SilentlyContinue)
            foreach ($cp in $conns) {
                if ($cp -and $cp.OwningProcess -gt 0) {
                    $savedPids += $cp.OwningProcess
                    $cChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($cp.OwningProcess)" -ErrorAction SilentlyContinue
                    foreach ($cc in $cChildren) {
                        $savedPids += $cc.ProcessId
                        $cGrand = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($cc.ProcessId)" -ErrorAction SilentlyContinue
                        foreach ($cg in $cGrand) { $savedPids += $cg.ProcessId }
                    }
                }
            }
        }

        $uniqPids = @($savedPids | Select-Object -Unique | Where-Object { $_ -gt 0 })
        $session.canvas_owned = $true
        $session.canvas_pids = $uniqPids
        Save-Session

        Log-Message "[OK] OpenHands Agent Canvas is READY at http://127.0.0.1:8000" "Green"
        Log-Message "     [OWNERSHIP] canvas_owned = true (launched by this session)" "DarkGray"
        Start-Process "http://127.0.0.1:8000"
    } else {
        Log-Message "[WARN] Agent Canvas did not respond in 60s. Check $canvasLog" "Yellow"
    }
}

Log-Message ""

# 4. Check if Mobile LAN PWA Gateway is already running on port 8443
$gatewayRunning = $false
try {
    $conn = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Log-Message "[OK] Mobile LAN PWA Gateway is ALREADY running on port 8443" "Green"
        Log-Message "     Reusing existing Gateway instance." "Gray"
        $gatewayRunning = $true
        if (-not $session.gateway_owned) {
            $session.gateway_owned = $false
            $session.gateway_pid = $null
            Log-Message "     [OWNERSHIP] gateway_owned = false (pre-existing instance, will NOT be stopped by STOP launcher)" "DarkGray"
        } else {
            Log-Message "     [OWNERSHIP] gateway_owned = true (managed by this session)" "DarkGray"
        }
    }
} catch {}

# Discover LAN IP and Hostname for PWA status reporting
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = "127.0.0.1" }
$hostname = $env:COMPUTERNAME

if (-not $gatewayRunning) {
    Log-Message "[4/4] Starting Mobile LAN PWA Gateway in background (HTTPS port 8443)..." "Cyan"

    $pwaLog = Join-Path $pwaLogDir "lan-gateway.log"
    Rotate-LogFile $pwaLog

    # Ensure certificate exists
    $pfxPath = Join-Path $ProjectRoot "openhands-pwa\certs\openhands-lan.pfx"
    if (-not (Test-Path $pfxPath)) {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-pwa\generate-certs.ps1") | Out-Null
    }

    $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $nodeExe) { $nodeExe = "C:\Program Files\nodejs\node.exe" }
    $gwScript = Join-Path $ProjectRoot "openhands-pwa\lan-gateway.mjs"
    $gwCmd = "cmd.exe /c `"`"$nodeExe`" `"$gwScript`" > `"$pwaLog`" 2>&1`""

    $wmiGwRes = $procClass.Create($gwCmd, (Join-Path $ProjectRoot "openhands-pwa"), $startupInstance)

    $gwReady = Wait-ForServiceReady -Port 8443 -TimeoutSeconds 15
    $c8443 = if ($gwReady) { Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 } else { $null }

    if ($gwReady) {
        $actualGwPid = if ($c8443 -and $c8443.OwningProcess -gt 0) { $c8443.OwningProcess } else { $wmiGwRes.ProcessId }
        $session.gateway_owned = $true
        $session.gateway_pid = $actualGwPid
        Log-Message "[OK] Mobile LAN PWA Gateway online in background (PID: $actualGwPid)" "Green"
        Log-Message "     LAN PWA URL: https://${lanIp}:8443 (or https://${hostname}:8443)" "Cyan"
        Log-Message "     [OWNERSHIP] gateway_owned = true (launched by this session)" "DarkGray"
    } else {
        Log-Message "[WARN] Mobile LAN PWA Gateway did not respond on 8443 within 15s. Check $pwaLog" "Yellow"
    }
}

# Save session.json
Save-Session

Log-Message ""
Log-Message "=====================================================================" "Cyan"
Log-Message "   OPENHANDS LOCAL IS ACTIVE at http://127.0.0.1:8000" "Green"
Log-Message "   MOBILE LAN PWA AVAILABLE at https://${lanIp}:8443" "Cyan"
Log-Message "=====================================================================" "Cyan"
Log-Message ""