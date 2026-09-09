# ik_llama Backend Rollback Script
# Location: K:\Project\OpenHands-Update\scripts\rollback-ik-llama.ps1

param(
    [string]$BackupPath = "",
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "ik-llama-rollback"

Log-Msg "=====================================================================" "WARN"
Log-Msg "               IK_LLAMA BACKEND ROLLBACK" "WARN"
Log-Msg "=====================================================================" "WARN"

$prodBinDir = Join-Path $Global:ProjectRootDir "ik_llama\bin"

if (-not $BackupPath) {
    $BackupPath = Get-LatestBackupPath "ik_llama"
}

if (-not $BackupPath -or (-not (Test-Path $BackupPath))) {
    Log-Msg "No valid backup found to rollback from!" "ERROR"
    exit 1
}

Log-Msg "Target backup folder: $BackupPath" "STEP"

# 1. Stop platform
Log-Msg "[1/4] Stopping active processes..." "STEP"
& (Join-Path $Global:ProjectRootDir ".openhands-local\stop.ps1")
Start-Sleep -Seconds 2

# Ensure any process specifically running binaries from ik_llama\bin is stopped so files can be replaced
$lockedProcs = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -like "$prodBinDir\*" -or
    $_.CommandLine -like "*$prodBinDir\llama-server.exe*"
}
foreach ($lp in $lockedProcs) {
    Log-Msg "      Stopping active backend process $($lp.Name) (PID: $($lp.ProcessId)) to release binary lock..." "INFO"
    Stop-Process -Id $lp.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# 2. Restore production bin
Log-Msg "[2/4] Restoring ik_llama\bin from backup..." "STEP"
Fast-CopyDir $BackupPath $prodBinDir -Mirror
Log-Msg "      Restored production binaries from: $BackupPath" "SUCCESS"

# 3. Platform Restart (Conditional on -RestartPlatform; default: STOPPED)
if ($RestartPlatform) {
    Log-Msg "[3/4] Starting OpenHands Local (-RestartPlatform supplied)..." "STEP"
    & (Join-Path $Global:ProjectRootDir ".openhands-local\start.ps1")
    Start-Sleep -Seconds 3

    # 4. Smoke test
    Log-Msg "[4/4] Running smoke test on restored backend..." "STEP"
    if (Test-HttpEndpoint "http://127.0.0.1:8080/v1/models") {
        Log-Msg "=====================================================================" "SUCCESS"
        Log-Msg "   ROLLBACK SUCCESSFUL: ik_llama restored and active on port 8080" "SUCCESS"
        Log-Msg "=====================================================================" "SUCCESS"
        exit 0
    } else {
        Log-Msg "Restored backend not responding on port 8080!" "ERROR"
        exit 1
    }
} else {
    Log-Msg "=====================================================================" "SUCCESS"
    Log-Msg "   ROLLBACK SUCCESSFUL: ik_llama restored to bin/ (Station STOPPED)" "SUCCESS"
    Log-Msg "   To start platform explicitly, run START-OPENHANDS-LOCAL.cmd" "INFO"
    Log-Msg "=====================================================================" "SUCCESS"
    exit 0
}

