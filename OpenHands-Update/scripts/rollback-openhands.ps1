# OpenHands Agent Canvas Rollback Script
# Location: K:\Project\OpenHands-Update\scripts\rollback-openhands.ps1

[CmdletBinding()]
param(
    [string]$BackupPath = "",
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "openhands-rollback"

Log-Msg "=====================================================================" "WARN"
Log-Msg "               OPENHANDS AGENT CANVAS ROLLBACK" "WARN"
Log-Msg "=====================================================================" "WARN"

$targetDir = "C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas"

if (-not $BackupPath) {
    $BackupPath = Get-LatestBackupPath "openhands"
}

if (-not $BackupPath -or (-not (Test-Path $BackupPath))) {
    Log-Msg "No valid backup found to rollback from!" "ERROR"
    exit 1
}

Log-Msg "Target backup folder: $BackupPath" "STEP"

# 1. Stop OpenHands Local cleanly using session ownership
Log-Msg "[1/4] Stopping active OpenHands processes..." "STEP"
& "K:\Project\.openhands-local\stop.ps1"
Start-Sleep -Seconds 2

# 2. Restore files from backup
Log-Msg "[2/4] Restoring Agent Canvas files from backup..." "STEP"
Fast-CopyDir $BackupPath $targetDir -Mirror

$pkg = Get-Content (Join-Path $targetDir "package.json") -Raw | ConvertFrom-Json
Log-Msg "      Restored package version: v$($pkg.version)" "SUCCESS"

# 3. Re-apply patches to ensure clean consistent state
Log-Msg "[3/4] Re-verifying localization and voice integration..." "STEP"
& powershell -NoProfile -ExecutionPolicy Bypass -File "K:\Project\openhands-localization\patch-agent-canvas-localization.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File "K:\Project\local-voice\patch-agent-canvas-voice.ps1"

# 4. Final State Handling (Station Stopped by default)
Log-Msg "[4/4] Rollback completed." "SUCCESS"
if ($RestartPlatform) {
    Log-Msg "Restarting platform per request..." "STEP"
    & "K:\Project\.openhands-local\start.ps1"
    Start-Sleep -Seconds 3
    $smokeOk = Run-SmokeTest -CheckLocale $true
    if (-not $smokeOk) {
        Log-Msg "Smoke test on restarted platform reported issues." "WARN"
        exit 1
    }
} else {
    Log-Msg "Station remains STOPPED per safety default." "INFO"
}

Log-Msg "=====================================================================" "SUCCESS"
Log-Msg "   ROLLBACK SUCCESSFUL: OpenHands restored to v$($pkg.version)" "SUCCESS"
Log-Msg "=====================================================================" "SUCCESS"
exit 0
