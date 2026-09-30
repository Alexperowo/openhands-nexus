<#
.SYNOPSIS
    Antigravity Nexus Station Supervisor.
    Location: Antigravity-Nexus/Supervisor/station.ps1

.DESCRIPTION
    Initializes and manages the physical hardware stack and sidecar services:
    - Dual-GPU pool (RTX 5060 Ti 16 GB + RTX 2080 Ti 22 GB) via NVML
    - Port :8080  — llama-swap Model Router (Dynamic VRAM Swapping)
    - Port :18002 — Local Voice Bridge (GigaAM v3 STT + Supertonic 3 TTS)
    - Port :18005 — Antigravity Bridge Router (Model Catalog & SSE Reasoner)
    - Sets CLOUD_CODE_URL for seamless Google Antigravity integration
#>

[CmdletBinding()]
param(
    [switch]$StatusOnly,
    [switch]$RestartServices
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (Test-Path (Join-Path $PSScriptRoot "Antigravity-Nexus")) {
    $ProjectRoot = (Resolve-Path $PSScriptRoot).Path
    $NexusRoot = (Resolve-Path (Join-Path $ProjectRoot "Antigravity-Nexus")).Path
} elseif (Test-Path (Join-Path $PSScriptRoot "Bridge")) {
    $NexusRoot = (Resolve-Path $PSScriptRoot).Path
    $ProjectRoot = (Resolve-Path (Join-Path $NexusRoot "..")).Path
} else {
    $NexusRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $ProjectRoot = (Resolve-Path (Join-Path $NexusRoot "..")).Path
}

$PythonExe = "C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"
$PythonWExe = "C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = "python.exe" }
if (-not (Test-Path $PythonWExe)) { $PythonWExe = "pythonw.exe" }

$SwapBin = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
$SwapConfig = Join-Path $ProjectRoot "llama-swap\config.yaml"
$VoiceScript = Join-Path $NexusRoot "Voice\service.py"
$BridgeScript = Join-Path $NexusRoot "Bridge\bridge.py"

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "        Antigravity Nexus Station — Unified Supervisor                 " -ForegroundColor White
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Dual-GPU Hardware Verification via NVML
Write-Host "[1/5] Inspecting Dual-GPU Hardware Pool..." -ForegroundColor Yellow
try {
    $vramRaw = & $PythonExe "$ProjectRoot\Config\vram_manager.py" --json 2>$null
    if ($vramRaw) {
        $vram = $vramRaw | ConvertFrom-Json
        foreach ($gpu in $vram.gpus) {
            $usedMb = $gpu.used_mb
            $totalMb = $gpu.total_mb
            $freeMb = $gpu.free_mb
            Write-Host "      GPU $($gpu.index): $($gpu.name) -> Free: $($freeMb) MiB / Total: $($totalMb) MiB (Used: $($usedMb) MiB)" -ForegroundColor Green
        }
    } else {
        Write-Host "      Dual-GPU NVML initialized (vram_manager fallback active)." -ForegroundColor DarkGray
    }
} catch {
    Write-Host "      Warning: Could not query NVML ($($_))." -ForegroundColor DarkYellow
}

# Helper: Wait for HTTP endpoint
function Test-HttpProbe([string]$url, [int]$timeoutSec = 3) {
    try {
        $res = Invoke-RestMethod -Uri $url -TimeoutSec $timeoutSec -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# Helper: Safe process termination by port and command line pattern
function Stop-ServiceByPortAndPattern([int]$port, [string]$pattern) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn -and $conn.OwningProcess -gt 0) {
        $pidToKill = $conn.OwningProcess
        $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $pidToKill" -ErrorAction SilentlyContinue
        if ($procInfo -and ($procInfo.CommandLine -match $pattern -or $procInfo.Name -match "python")) {
            Write-Host "      Stopping existing process on port $port (PID: $pidToKill)..." -ForegroundColor Yellow
            try {
                Stop-Process -Id $pidToKill -ErrorAction Stop
            } catch {
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 1
        }
    }
}

if ($RestartServices) {
    Write-Host "      [-RestartServices active] Stopping running Nexus sidecars..." -ForegroundColor Cyan
    Stop-ServiceByPortAndPattern 18005 "bridge\.py"
    Stop-ServiceByPortAndPattern 18002 "service\.py"
}

# 2. Port :8080 (llama-swap)
Write-Host "[2/5] Inspecting llama-swap Model Router (:8080)..." -ForegroundColor Yellow
$conn8080 = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn8080 -and -not $StatusOnly) {
    if (Test-Path $SwapBin) {
        Write-Host "      Launching llama-swap on port 8080..." -ForegroundColor Cyan
        Start-Process -FilePath $SwapBin -ArgumentList "-config `"$SwapConfig`" -watch-config -listen 127.0.0.1:8080" -WorkingDirectory (Join-Path $ProjectRoot "llama-swap") -WindowStyle Hidden
        Start-Sleep -Seconds 2
    } else {
        Write-Host "      Error: llama-swap.exe binary not found at $SwapBin" -ForegroundColor Red
    }
}
$isSwapHealthy = Test-HttpProbe "http://127.0.0.1:8080/v1/models" 3
if ($isSwapHealthy) {
    Write-Host "      llama-swap is ONLINE and healthy at http://127.0.0.1:8080" -ForegroundColor Green
} else {
    Write-Host "      llama-swap status: PENDING / OFFLINE" -ForegroundColor Yellow
}

# 3. Port :18002 (Local Voice Bridge)
Write-Host "[3/5] Inspecting Local Voice Bridge (:18002)..." -ForegroundColor Yellow
$conn18002 = Get-NetTCPConnection -LocalPort 18002 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$needVoiceStart = (-not $conn18002)
if ($conn18002 -and -not $StatusOnly) {
    $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn18002.OwningProcess)" -ErrorAction SilentlyContinue
    if ($procInfo -and $procInfo.CommandLine -notmatch [regex]::Escape($NexusRoot)) {
        Write-Host "      Found legacy Voice process outside NexusRoot. Upgrading..." -ForegroundColor Cyan
        Stop-ServiceByPortAndPattern 18002 "service\.py"
        $needVoiceStart = $true
    }
}
if ($needVoiceStart -and -not $StatusOnly) {
    Write-Host "      Launching Local Voice Bridge (GigaAM v3 STT + Supertonic 3 TTS)..." -ForegroundColor Cyan
    Start-Process -FilePath $PythonWExe -ArgumentList "`"$VoiceScript`" 18002" -WorkingDirectory (Join-Path $NexusRoot "Voice") -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
$isVoiceHealthy = Test-HttpProbe "http://127.0.0.1:18002/health" 3
if ($isVoiceHealthy) {
    Write-Host "      Voice Bridge is ONLINE and healthy at http://127.0.0.1:18002" -ForegroundColor Green
} else {
    Write-Host "      Voice Bridge status: PENDING / OFFLINE" -ForegroundColor Yellow
}

# 4. Port :18005 (Antigravity Bridge)
Write-Host "[4/5] Inspecting Antigravity Bridge Router (:18005)..." -ForegroundColor Yellow
$conn18005 = Get-NetTCPConnection -LocalPort 18005 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$needBridgeStart = (-not $conn18005)
if ($conn18005 -and -not $StatusOnly) {
    $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn18005.OwningProcess)" -ErrorAction SilentlyContinue
    if ($procInfo -and $procInfo.CommandLine -notmatch [regex]::Escape($NexusRoot)) {
        Write-Host "      Found legacy Bridge process outside NexusRoot (PID $($conn18005.OwningProcess)). Upgrading to hardened Nexus Bridge..." -ForegroundColor Cyan
        Stop-ServiceByPortAndPattern 18005 "bridge\.py"
        $needBridgeStart = $true
    }
}
if ($needBridgeStart -and -not $StatusOnly) {
    Write-Host "      Launching Antigravity Bridge Router on port 18005..." -ForegroundColor Cyan
    Start-Process -FilePath $PythonWExe -ArgumentList "`"$BridgeScript`"" -WorkingDirectory (Join-Path $NexusRoot 'Bridge') -WindowStyle Hidden
    Start-Sleep -Seconds 3
}
$isBridgeHealthy = Test-HttpProbe "http://127.0.0.1:18005/health" 3
if ($isBridgeHealthy) {
    Write-Host "      Antigravity Bridge is ONLINE and healthy at http://127.0.0.1:18005" -ForegroundColor Green
} else {
    Write-Host "      Antigravity Bridge status: PENDING / OFFLINE" -ForegroundColor Yellow
}

# 5. Environment & Station Integration
Write-Host "[5/5] Configuring Environment Integration..." -ForegroundColor Yellow
if (-not $StatusOnly) {
    [Environment]::SetEnvironmentVariable("CLOUD_CODE_URL", "http://127.0.0.1:18005", "User")
    $env:CLOUD_CODE_URL = "http://127.0.0.1:18005"
}
$currCloudCode = [Environment]::GetEnvironmentVariable("CLOUD_CODE_URL", "User")
Write-Host "      Active CLOUD_CODE_URL: $currCloudCode" -ForegroundColor Green

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "   Antigravity Nexus Ready: Launch Antigravity to access models       " -ForegroundColor White
Write-Host "   Station Model Lineup in Antigravity Dropdown:                       " -ForegroundColor Cyan
Write-Host "     - Station: Qwen 27B Coder (Vision)                                " -ForegroundColor DarkCyan
Write-Host "     - Station: Next 80B MoE (Thinking)                                " -ForegroundColor DarkCyan
Write-Host "     - Station: Ornith 1.5 35B (Android and Big Dumps)                 " -ForegroundColor DarkCyan
Write-Host "     - Station: Tinfield 177B (Titan MoE)                              " -ForegroundColor DarkCyan
Write-Host "     - Station: Qwen 122B MoE (208E + Streaming Translation)           " -ForegroundColor DarkCyan
Write-Host "   Emergency Safe-Switch: Launchers\SAFE-SWITCH.cmd                    " -ForegroundColor DarkGray
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""
