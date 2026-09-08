# stop-swap.ps1 - Safe ownership-aware stopper for llama-swap
$ErrorActionPreference = "Continue"

$swapDir = "K:\Project\llama-swap"
$sessionFile = Join-Path $swapDir "session.json"

Write-Host "=== STOPPING LLAMA-SWAP ===" -ForegroundColor Yellow

if (-not (Test-Path $sessionFile)) {
    Write-Host "[INFO] No active session.json found. No owned processes to terminate." -ForegroundColor Gray
    exit 0
}

$sess = $null
try {
    $sess = Get-Content $sessionFile -Raw | ConvertFrom-Json
} catch {
    Write-Host "[WARN] Could not parse session.json." -ForegroundColor Yellow
}

if (-not $sess) {
    Remove-Item $sessionFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$port = if ($sess.port) { $sess.port } else { 8080 }

if ($sess.owned -eq $true -and $sess.pid) {
    $targetPid = [int]$sess.pid
    Write-Host "[*] Requesting models unload via API..." -ForegroundColor Cyan
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/models/unload" -Method Post -TimeoutSec 5 -ErrorAction SilentlyContinue
    } catch {}
    Start-Sleep -Milliseconds 500

    Write-Host "[*] Terminating owned llama-swap process (PID: $targetPid)..." -ForegroundColor Cyan
    try {
        $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $targetPid" -ErrorAction SilentlyContinue
        if ($procInfo) {
            $pName = $procInfo.Name.ToLower()
            if ($pName -in @('llama-swap.exe', 'cmd.exe')) {
                # Stop any child processes first
                $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $targetPid" -ErrorAction SilentlyContinue
                foreach ($c in $children) {
                    Write-Host "    Stopping child process: $($c.Name) (PID: $($c.ProcessId))" -ForegroundColor Yellow
                    Stop-Process -Id $c.ProcessId -Force -ErrorAction SilentlyContinue
                }
                Write-Host "    [STOP] Stopping owned llama-swap (PID: $targetPid)" -ForegroundColor Yellow
                Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
            } else {
                Write-Host "    [SKIP] PID $targetPid is $pName, not llama-swap. Skipped." -ForegroundColor Gray
            }
        } else {
            Write-Host "    [INFO] Process PID $targetPid was already terminated." -ForegroundColor Gray
        }
    } catch {
        Write-Host "    [INFO] Process PID $targetPid error/already terminated." -ForegroundColor Gray
    }
} else {
    Write-Host "[SKIP] llama-swap was NOT started by this session (owned = false). Keeping it running." -ForegroundColor Gray
}

Remove-Item $sessionFile -Force -ErrorAction SilentlyContinue
Write-Host "=== LLAMA-SWAP STOP FINISHED ===" -ForegroundColor Yellow
