$ErrorActionPreference = "Continue"

Write-Host "Recycling Agent Canvas & OpenHands Core..." -ForegroundColor Cyan

# Terminate processes on 8000, 3001, 18000, 18001
$ports = @(8000, 3001, 18000, 18001)
foreach ($pt in $ports) {
    $conns = @(Get-NetTCPConnection -LocalPort $pt -State Listen -ErrorAction SilentlyContinue)
    foreach ($c in $conns) {
        if ($c -and $c.OwningProcess -gt 0) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Seconds 2

# Clean up any lingering node/cmd related to canvas
$lingering = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.CommandLine -like '*agent-canvas*' -or $_.CommandLine -like '*static-server.mjs*') -and
    ($_.Name -in @('node.exe', 'cmd.exe', 'agent-canvas.exe'))
}
foreach ($proc in $lingering) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}

Start-Sleep -Seconds 2

# Start agent-canvas via WMI
$procClass = [wmiclass]'Win32_Process'
$startup = [wmiclass]'Win32_ProcessStartup'
$startupInstance = $startup.CreateInstance()
$startupInstance.ShowWindow = 0

$canvasLog = "K:\Project\Logs\OpenHands\agent-canvas.log"
$canvasCmd = "cmd.exe /c set INGRESS_HOST=127.0.0.1 && agent-canvas.cmd >> `"$canvasLog`" 2>&1"

$res = $procClass.Create($canvasCmd, "K:\Project", $startupInstance)
Write-Host "Spawned Canvas Launcher PID: $($res.ProcessId)" -ForegroundColor Green

# Wait for 18000 and 8000
$ready = $false
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    $c8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    $c18000 = Get-NetTCPConnection -LocalPort 18000 -State Listen -ErrorAction SilentlyContinue
    if ($c8000 -and $c18000) {
        $ready = $true
        break
    }
}

Write-Host "Canvas & Core Ready: $ready" -ForegroundColor Cyan
