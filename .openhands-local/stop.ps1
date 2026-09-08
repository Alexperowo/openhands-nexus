# OpenHands Local Shutdown Script
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host "               STOPPING OPENHANDS LOCAL PLATFORM" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host ""

$pidDir = $PSScriptRoot
$sessionFile = Join-Path $pidDir "session.json"

function Stop-OwnedProcess([int]$id) {
    try {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    } catch {}
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId = $id" -ErrorAction SilentlyContinue
        if ($p) {
            $null = $p | Invoke-CimMethod -MethodName Terminate -ErrorAction SilentlyContinue
        }
    } catch {}
}

if (-not (Test-Path $sessionFile)) {
    Write-Host "[INFO] No active session.json found. No owned processes to terminate." -ForegroundColor Gray
} else {
    $session = $null
    try {
        $session = Get-Content $sessionFile -Raw | ConvertFrom-Json
    } catch {
        Write-Host "[WARN] Could not parse session.json." -ForegroundColor Yellow
    }

    if ($session) {
        # 1. Handle Agent Canvas processes (only if canvas_owned == true)
        if ($session.canvas_owned -eq $true) {
            Write-Host "[*] Terminating launcher-owned Agent Canvas processes..." -ForegroundColor Cyan
            $pids = @($session.canvas_pids | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
            
            # Dynamically collect any child/grandchild processes strictly descended from recorded canvas PIDs (proven ancestry)
            $allOwnedPids = [System.Collections.Generic.List[int]]::new()
            foreach ($p in $pids) {
                if (-not $allOwnedPids.Contains($p)) { $allOwnedPids.Add($p) }
            }
            foreach ($p in $pids) {
                try {
                    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $p" -ErrorAction SilentlyContinue
                    foreach ($c in $children) {
                        if (-not $allOwnedPids.Contains($c.ProcessId)) { $allOwnedPids.Add($c.ProcessId) }
                        $grandchildren = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($c.ProcessId)" -ErrorAction SilentlyContinue
                        foreach ($gc in $grandchildren) {
                            if (-not $allOwnedPids.Contains($gc.ProcessId)) { $allOwnedPids.Add($gc.ProcessId) }
                        }
                    }
                } catch {}
            }

            foreach ($pidVal in $allOwnedPids) {
                try {
                    $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $pidVal" -ErrorAction SilentlyContinue
                    if ($procInfo) {
                        $pName = $procInfo.Name.ToLower()
                        if ($pName -in @('cmd.exe', 'node.exe', 'agent-canvas.exe', 'uv.exe', 'uvx.exe', 'uvicorn.exe', 'python.exe', 'powershell.exe', 'conhost.exe')) {
                            Write-Host ("[STOP] Stopping owned Agent Canvas process: " + $procInfo.Name + " (PID: " + $pidVal + ")") -ForegroundColor Yellow
                            Stop-OwnedProcess -id $pidVal
                        } else {
                            Write-Host ("[SKIP] PID " + $pidVal + " belongs to unrelated process (" + $procInfo.Name + "). Skipped.") -ForegroundColor Gray
                        }
                    } else {
                        Write-Host ("[INFO] Process PID " + $pidVal + " was already terminated.") -ForegroundColor Gray
                    }
                } catch {
                    Write-Host ("[INFO] Process PID " + $pidVal + " error/already terminated.") -ForegroundColor Gray
                }
            }
        } else {
            Write-Host "[SKIP] Agent Canvas was NOT started by this launcher (canvas_owned=false). Keeping it running." -ForegroundColor Gray
        }

        # 2. Handle llama-swap router (only if swap_owned == true)
        if ($session.swap_owned -eq $true -and $session.swap_pid) {
            $spid = [int]$session.swap_pid
            Write-Host "[*] Requesting models unload via llama-swap API..." -ForegroundColor Cyan
            try {
                $null = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/models/unload" -Method Post -TimeoutSec 5 -ErrorAction SilentlyContinue
            } catch {}
            Start-Sleep -Milliseconds 500

            Write-Host "[*] Terminating launcher-owned llama-swap process (PID: $spid)..." -ForegroundColor Cyan
            try {
                $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $spid" -ErrorAction SilentlyContinue
                if ($procInfo) {
                    $pName = $procInfo.Name.ToLower()
                    if ($pName -in @('llama-swap.exe', 'cmd.exe')) {
                        # Stop any child processes descended from this swap process
                        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $spid" -ErrorAction SilentlyContinue
                        foreach ($c in $children) {
                            Write-Host "    Stopping child process: $($c.Name) (PID: $($c.ProcessId))" -ForegroundColor Yellow
                            Stop-OwnedProcess -id $c.ProcessId
                        }
                        Write-Host ("[STOP] Stopping owned llama-swap (PID: " + $spid + ")") -ForegroundColor Yellow
                        Stop-OwnedProcess -id $spid
                    } else {
                        Write-Host ("[SKIP] PID " + $spid + " is $pName, not llama-swap. Skipped.") -ForegroundColor Gray
                    }
                } else {
                    Write-Host ("[INFO] llama-swap PID " + $spid + " was already terminated.") -ForegroundColor Gray
                }
            } catch {
                Write-Host ("[INFO] llama-swap PID " + $spid + " error/already terminated.") -ForegroundColor Gray
            }
        } elseif ($session.swap_owned -eq $false) {
            Write-Host "[SKIP] llama-swap was NOT started by this launcher (swap_owned=false). Keeping it running." -ForegroundColor Gray
        }

        # Legacy fallback for older sessions
        if ($session.llama_owned -eq $true -and $session.llama_pid) {
            $lpid = [int]$session.llama_pid
            try {
                $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $lpid" -ErrorAction SilentlyContinue
                if ($procInfo -and $procInfo.Name.ToLower() -eq "llama-server.exe") {
                    Stop-OwnedProcess -id $lpid
                }
            } catch {}
        }

        # 3. Handle Voice Bridge process (only if voice_owned == true)
        if ($session.voice_owned -eq $true -and $session.voice_pid) {
            $vpid = [int]$session.voice_pid
            Write-Host "[*] Terminating launcher-owned Voice Bridge process (PID: $vpid)..." -ForegroundColor Cyan
            try {
                # Attempt graceful shutdown via HTTP first
                try {
                    $null = Invoke-RestMethod -Uri "http://127.0.0.1:18002/shutdown" -Method Post -TimeoutSec 1 -ErrorAction SilentlyContinue
                } catch {}
                Start-Sleep -Milliseconds 500

                $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $vpid" -ErrorAction SilentlyContinue
                if ($procInfo) {
                    Write-Host ("[STOP] Stopping owned Voice Bridge (PID: " + $vpid + ")") -ForegroundColor Yellow
                    Stop-OwnedProcess -id $vpid
                } else {
                    Write-Host ("[INFO] Voice Bridge PID " + $vpid + " was already terminated.") -ForegroundColor Gray
                }
            } catch {
                Write-Host ("[INFO] Voice Bridge PID " + $vpid + " error/already terminated.") -ForegroundColor Gray
            }
        } else {
            Write-Host "[SKIP] Voice Bridge was NOT started by this launcher (voice_owned=false). Keeping it running." -ForegroundColor Gray
        }

        # 4. Handle Mobile LAN PWA Gateway (only if gateway_owned == true)
        if ($session.gateway_owned -eq $true -and $session.gateway_pid) {
            $gpid = [int]$session.gateway_pid
            Write-Host "[*] Terminating launcher-owned Mobile LAN PWA Gateway (PID: $gpid)..." -ForegroundColor Cyan
            try {
                $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $gpid" -ErrorAction SilentlyContinue
                if ($procInfo) {
                    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $gpid" -ErrorAction SilentlyContinue
                    foreach ($c in $children) {
                        Write-Host "    Stopping child process: $($c.Name) (PID: $($c.ProcessId))" -ForegroundColor Yellow
                        Stop-OwnedProcess -id $c.ProcessId
                    }
                    Write-Host ("[STOP] Stopping owned Gateway: " + $procInfo.Name + " (PID: " + $gpid + ")") -ForegroundColor Yellow
                    Stop-OwnedProcess -id $gpid
                } else {
                    Write-Host ("[INFO] Gateway PID " + $gpid + " was already terminated.") -ForegroundColor Gray
                }
            } catch {
                Write-Host ("[INFO] Gateway PID " + $gpid + " error/already terminated.") -ForegroundColor Gray
            }
        } elseif ($session.gateway_owned -eq $false) {
            Write-Host "[SKIP] Gateway was NOT started by this launcher (gateway_owned=false). Keeping it running." -ForegroundColor Gray
        }

        # Delete session.json after stopping
        Remove-Item $sessionFile -Force -ErrorAction SilentlyContinue
    }
}

# Remove legacy pid files
Remove-Item (Join-Path $pidDir "llama-server.pid") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $pidDir "agent-canvas.pid") -Force -ErrorAction SilentlyContinue

# 4b. Cleanup any orphan processes belonging to this project on known ports
$knownPorts = @(8000, 8080, 8443, 18000, 18001, 18002)
foreach ($pt in $knownPorts) {
    $conns = @(Get-NetTCPConnection -LocalPort $pt -State Listen -ErrorAction SilentlyContinue)
    foreach ($c in $conns) {
        if ($c -and $c.OwningProcess -gt 0) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($c.OwningProcess)" -ErrorAction SilentlyContinue
            if ($proc) {
                $cmdline = $proc.CommandLine
                $pname = $proc.Name.ToLower()
                if ($cmdline -match "llama-swap|local-voice|lan-gateway|agent-canvas|agent-server|openhands" -or $pname -eq "llama-swap.exe") {
                    Write-Host "[STOP] Terminating orphan project process on port ${pt}: $($proc.Name) (PID: $($proc.ProcessId))" -ForegroundColor Yellow
                    $ch = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($proc.ProcessId)" -ErrorAction SilentlyContinue
                    foreach ($chi in $ch) { Stop-OwnedProcess -id $chi.ProcessId }
                    Stop-OwnedProcess -id $proc.ProcessId
                }
            }
        }
    }
}

Start-Sleep -Seconds 1
Write-Host ""

# 5. Read-only port status check (NEVER kills anything)
$checkPorts = @(8000, 8080, 8443, 18000, 18001, 18002)
$activePorts = @()
foreach ($p in $checkPorts) {
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) {
        $activePorts += $p
    }
}

if ($activePorts.Count -eq 0) {
    Write-Host "[STATUS] All OpenHands ports (8000, 8080, 8443, 18000, 18001, 18002) are free." -ForegroundColor Green
} else {
    Write-Host ("[STATUS] Active listening ports remaining: " + ($activePorts -join ", ")) -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host "                   OPENHANDS LOCAL STOPPED" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host ""