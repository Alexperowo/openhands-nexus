# start-swap.ps1 - Safe ownership-aware launcher for llama-swap
$ErrorActionPreference = "Continue"

$swapDir = "K:\Project\llama-swap"
$binExe = Join-Path $swapDir "bin\llama-swap.exe"
$cfgFile = Join-Path $swapDir "config.yaml"
$sessionFile = Join-Path $swapDir "session.json"
$logDir = Join-Path $swapDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "llama-swap.log"

$port = 8080
if ($args.Count -gt 0 -and $args[0] -match '^\d+$') {
    $port = [int]$args[0]
}

Write-Host "=== STARTING LLAMA-SWAP (Port: $port) ===" -ForegroundColor Cyan

# 1. Check if already running on port
$alreadyRunning = $false
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -ErrorAction Stop
    if ($h -eq "OK") {
        $alreadyRunning = $true
    }
} catch {}

if ($alreadyRunning) {
    Write-Host "[OK] llama-swap is ALREADY running on port $port." -ForegroundColor Green
    Write-Host "     [OWNERSHIP] owned = false (foreign/pre-existing, will NOT be stopped by STOP)" -ForegroundColor DarkGray
    $sess = @{
        owned = $false
        pid = $null
        port = $port
    }
    $sess | ConvertTo-Json | Set-Content -Path $sessionFile -Encoding UTF8
    exit 0
}

# 2. Check if port is blocked by unrecognized process
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "[ERROR] Port $port is occupied by an unrecognized process (PID: $($conn.OwningProcess)). Aborting." -ForegroundColor Red
    exit 1
}

# 3. Start llama-swap
Write-Host "[*] Launching llama-swap in background..." -ForegroundColor Cyan
$procClass = [wmiclass]"Win32_Process"
$startup = [wmiclass]"Win32_ProcessStartup"
$startupInstance = $startup.CreateInstance()
$startupInstance.ShowWindow = 0

$cmdLine = "cmd.exe /c `"`"$binExe`" -config `"$cfgFile`" -listen 127.0.0.1:$port > `"$logFile`" 2>&1`""
$wmiRes = $procClass.Create($cmdLine, $swapDir, $startupInstance)

$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -ErrorAction Stop
        if ($h -eq "OK") {
            $ready = $true
            break
        }
    } catch {}
}

if ($ready) {
    $connAfter = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $actualPid = if ($connAfter -and $connAfter.OwningProcess -gt 0) { $connAfter.OwningProcess } else { $wmiRes.ProcessId }
    
    $sess = @{
        owned = $true
        pid = $actualPid
        port = $port
    }
    $sess | ConvertTo-Json | Set-Content -Path $sessionFile -Encoding UTF8
    Write-Host "[OK] llama-swap online on port $port (PID: $actualPid)" -ForegroundColor Green
    Write-Host "     [OWNERSHIP] owned = true (launched by this session)" -ForegroundColor DarkGray
} else {
    Write-Host "[ERROR] llama-swap failed to respond on port $port within 20s. Check $logFile" -ForegroundColor Red
    exit 1
}
