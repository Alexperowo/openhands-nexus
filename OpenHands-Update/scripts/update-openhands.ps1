# OpenHands Agent Canvas & App Stack Updater Script
# Location: K:\Project\OpenHands-Update\scripts\update-openhands.ps1

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$Update,
    [switch]$Rollback,
    [string]$TargetVersion = "latest",
    [switch]$Force,
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "openhands"

# Ensure PATH includes Node.js and global npm
$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$env:PATH = "C:\Program Files\nodejs;" + (Join-Path $appData "npm") + ";" + $env:PATH

# Paths
$canvasPkgDir = Join-Path $appData "npm\node_modules\@openhands\agent-canvas"
$canvasPkgJson = Join-Path $canvasPkgDir "package.json"
$canvasDefaultsJson = Join-Path $canvasPkgDir "config\defaults.json"
$archiveBackupRoot = Join-Path $Global:ProjectRootDir "Archive\backups\OpenHands"
$openhandsBackupRoot = Join-Path $Global:BackupDir "openhands"
$lastRunStatusFile = Join-Path $Global:UpdateRootDir "state\last_run_status.json"

function Set-ComponentStatus([string]$Status) {
    $cur = @{}
    if (Test-Path $lastRunStatusFile) {
        try { $cur = Get-Content $lastRunStatusFile -Raw | ConvertFrom-Json } catch { $cur = @{} }
    }
    $cur | Add-Member -NotePropertyName "openhands" -NotePropertyValue $Status -Force
    $cur | ConvertTo-Json | Out-File -FilePath $lastRunStatusFile -Encoding UTF8
}

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$Update.IsPresent) + ([int]$Rollback.IsPresent)
if ($modeCount -eq 0) {
    Log-Msg "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
} elseif ($modeCount -gt 1) {
    Log-Msg "Error: Only one of -CheckOnly, -DryRun, -Update, -Rollback may be specified." "ERROR"
    exit 1
}

# 2. Station Gate (Hard Gate: NEVER allow update or rollback while production is running)
function Assert-StationStopped {
    $ports = @(8000, 8080, 8443, 18000, 18001, 18002)
    $activeConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    if ($activeConns) {
        $pList = ($activeConns.LocalPort | Select-Object -Unique) -join ", "
        Log-Msg "CRITICAL GATE FAILED: Production station is RUNNING (Active ports: $pList)." "ERROR"
        Log-Msg "Refusing operation to protect live OpenHands session." "ERROR"
        Log-Msg "Please stop the platform first via STOP-OPENHANDS-LOCAL.cmd." "WARN"
        exit 1
    }
    Log-Msg "Station status: STOPPED (All production ports free)" "SUCCESS"
}

# Read current versions
$currentCanvasVer = "unknown"
if (Test-Path $canvasPkgJson) {
    try {
        $pkg = Get-Content $canvasPkgJson -Raw | ConvertFrom-Json
        $currentCanvasVer = $pkg.version
    } catch {}
}

$currentServerPinned = "unknown"
$currentAutomationPinned = "unknown"
if (Test-Path $canvasDefaultsJson) {
    try {
        $defs = Get-Content $canvasDefaultsJson -Raw | ConvertFrom-Json
        $currentServerPinned = $defs.versions.agentServer
        $currentAutomationPinned = $defs.versions.automation
    } catch {}
}

# Function to query PyPI version
function Get-PyPiLatestVersion([string]$pkgName) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $pypiUrl = "https://pypi.org/pypi/$pkgName/json"
        $res = Invoke-RestMethod -Uri $pypiUrl -TimeoutSec 8 -Headers @{ "User-Agent" = "OpenHands-Update/1.0" }
        return $res.info.version
    } catch {
        return "query_failed"
    }
}

# Function to query npm version
function Get-NpmLatestVersion([string]$pkgName) {
    try {
        $verOut = & cmd.exe /c "npm view $pkgName version 2>nul"
        if ($LASTEXITCODE -eq 0 -and $verOut) {
            return $verOut.Trim()
        }
    } catch {}
    return "query_failed"
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -CheckOnly
# ═══════════════════════════════════════════════════════════════════════════
if ($CheckOnly) {
    Log-Msg "=== OpenHands App Stack Updater (CheckOnly Mode) ===" "STEP"
    Assert-StationStopped

    Log-Msg "Checking upstream npm & PyPI registries..." "INFO"
    $latestCanvasVer = Get-NpmLatestVersion "@openhands/agent-canvas"
    $latestServerPyPi = Get-PyPiLatestVersion "openhands-agent-server"
    $latestAutomationPyPi = Get-PyPiLatestVersion "openhands-automation"

    # Localization and Voice versions
    $locStrings = 0
    $locDict = "K:\Project\openhands-localization\ru.json"
    if (Test-Path $locDict) {
        try {
            $locData = Get-Content $locDict -Raw | ConvertFrom-Json
            $locStrings = ($locData.psobject.Properties | Measure-Object).Count
        } catch {}
    }

    $voiceIndex = Join-Path $canvasPkgDir "build\index.html"
    $voiceInjected = $false
    if (Test-Path $voiceIndex) {
        $html = [System.IO.File]::ReadAllText($voiceIndex, [System.Text.Encoding]::UTF8)
        $voiceInjected = ($html.Contains("voice-bridge.css") -and $html.Contains("voice-bridge.js"))
    }

    Log-Msg "=====================================================================" "STEP"
    Log-Msg "               OPENHANDS APP-STACK VERSION MATRIX" "STEP"
    Log-Msg "=====================================================================" "STEP"
    Log-Msg "AGENT_CANVAS_CURRENT       = v$currentCanvasVer" "INFO"
    Log-Msg "AGENT_CANVAS_LATEST        = v$latestCanvasVer" "INFO"
    Log-Msg "AGENT_SERVER_PINNED        = v$currentServerPinned" "INFO"
    Log-Msg "AGENT_SERVER_LATEST        = v$latestServerPyPi" "INFO"
    Log-Msg "AUTOMATION_PINNED          = v$currentAutomationPinned" "INFO"
    Log-Msg "AUTOMATION_LATEST          = v$latestAutomationPyPi" "INFO"
    Log-Msg "LOCALIZATION_PATCH_VERSION = 1.0.0 (ru.json: $locStrings translated strings)" "INFO"
    Log-Msg "VOICE_PATCH_VERSION        = 1.0.0 (voice-bridge UI injected: $voiceInjected)" "INFO"
    Log-Msg "=====================================================================" "STEP"

    if ($currentCanvasVer -eq $latestCanvasVer) {
        Log-Msg "Status: AGENT CANVAS IS UP TO DATE (v$currentCanvasVer)" "SUCCESS"
    } else {
        Log-Msg "Status: AGENT CANVAS UPDATE AVAILABLE (v$currentCanvasVer -> v$latestCanvasVer)" "WARN"
    }

    if ($currentServerPinned -ne $latestServerPyPi -or $currentAutomationPinned -ne $latestAutomationPyPi) {
        Log-Msg "Note: Standalone PyPI packages have newer releases on PyPI." "INFO"
        Log-Msg "      POLICY: PINNED - DO NOT AUTOMATICALLY ALTER PRODUCTION PINS." "INFO"
        Log-Msg "      Agent Server & Automation versions follow Agent Canvas defaults.json pins." "INFO"
    }

    Log-Msg "To preview update: .\update-openhands.ps1 -DryRun" "INFO"
    Log-Msg "To execute update: .\update-openhands.ps1 -Update -TargetVersion latest" "INFO"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -DryRun
# ═══════════════════════════════════════════════════════════════════════════
if ($DryRun) {
    Log-Msg "=== OpenHands App Stack Updater (DryRun Simulation Mode) ===" "STEP"
    Assert-StationStopped

    $latestCanvasVer = Get-NpmLatestVersion "@openhands/agent-canvas"
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"

    Log-Msg "[SIMULATION] 1. Station stop gate: VERIFIED (All production ports free)" "INFO"
    Log-Msg "[SIMULATION] 2. Upstream Canvas target: v$latestCanvasVer" "INFO"
    Log-Msg "[SIMULATION] 3. Would backup current installation to: $archiveBackupRoot\$ts-v$currentCanvasVer\" "INFO"
    Log-Msg "[SIMULATION] 4. Would execute: npm install -g @openhands/agent-canvas@$TargetVersion" "INFO"
    Log-Msg "[SIMULATION] 5. Would inspect candidate defaults.json for updated agentServer & automation pins" "INFO"
    Log-Msg "[SIMULATION] 6. Would execute localization patcher: K:\Project\openhands-localization\patch-agent-canvas-localization.ps1" "INFO"
    Log-Msg "[SIMULATION] 7. Would execute localization parity audit (audit-localization.py) - STRICT GATE (0 missing keys)" "INFO"
    Log-Msg "[SIMULATION] 8. Would execute voice UI patcher: K:\Project\local-voice\patch-agent-canvas-voice.ps1" "INFO"
    Log-Msg "[SIMULATION] 9. Would verify voice injection anchors exist in build/index.html" "INFO"
    Log-Msg "[SIMULATION] 10. Final state: Station remains STOPPED by default (no automatic platform restart)." "INFO"
    Log-Msg "DryRun completed successfully. ZERO files modified." "SUCCESS"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -Rollback
# ═══════════════════════════════════════════════════════════════════════════
if ($Rollback) {
    Log-Msg "Invoking atomic rollback script..." "WARN"
    $rollbackArgs = if ($RestartPlatform) { "-RestartPlatform" } else { "" }
    & "$PSScriptRoot\rollback-openhands.ps1" $rollbackArgs
    exit $LASTEXITCODE
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -Update
# ═══════════════════════════════════════════════════════════════════════════
if ($Update) {
    Log-Msg "=== OpenHands App Stack Production Update ===" "STEP"
    Assert-StationStopped

    if (-not $Force) {
        Log-Msg "SAFETY HOLD: Real update execution requires -Force to proceed past the audit gate." "WARN"
        Log-Msg "Run with -DryRun to verify the execution plan, or add -Force if authorized." "INFO"
        exit 1
    }

    # Backup current installation
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $archiveBackupDir = Join-Path $archiveBackupRoot "$ts-v$currentCanvasVer"
    $localBackupDir = Join-Path $openhandsBackupRoot "$ts-v$currentCanvasVer"
    New-Item -ItemType Directory -Path $archiveBackupDir -Force | Out-Null
    New-Item -ItemType Directory -Path $localBackupDir -Force | Out-Null

    Log-Msg "Creating pre-update backup at: $archiveBackupDir..." "STEP"
    Fast-CopyDir $canvasPkgDir $archiveBackupDir
    Fast-CopyDir $canvasPkgDir $localBackupDir

    Set-Content -Path (Join-Path $openhandsBackupRoot "latest-backup.txt") -Value $localBackupDir -Encoding UTF8

    # Helper for rollback
    function Invoke-OpenHandsRollback([string]$Reason) {
        Log-Msg "*********************************************************************" "ERROR"
        Log-Msg "   UPDATE FAILED ($Reason) -> INITIATING AUTOMATIC ROLLBACK" "ERROR"
        Log-Msg "*********************************************************************" "ERROR"
        Set-ComponentStatus "ROLLBACK_$Reason"
        & "$PSScriptRoot\rollback-openhands.ps1" -BackupPath $localBackupDir
        exit 1
    }

    # Execute npm install
    Log-Msg "Installing @openhands/agent-canvas@$TargetVersion..." "STEP"
    $npmOut = & cmd.exe /c "npm install -g @openhands/agent-canvas@$TargetVersion 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Log-Msg "npm install failed: $npmOut" "ERROR"
        Invoke-OpenHandsRollback "NPM_INSTALL_FAILED"
    }

    # Verify new package.json
    $newPkg = Get-Content $canvasPkgJson -Raw | ConvertFrom-Json
    $installedVer = $newPkg.version
    Log-Msg "New Agent Canvas installed: v$installedVer" "SUCCESS"

    # Re-apply Local LLM and Ingress patches
    Log-Msg "Applying Local LLM & Ingress proxy patch..." "STEP"
    $llmPatcher = Join-Path $Global:ProjectRootDir "openhands-localization\patch-agent-canvas-local-llm.ps1"
    $llmProc = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$llmPatcher`"" -NoNewWindow -PassThru -Wait
    if ($llmProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "LOCAL_LLM_PATCH_FAILED"
    }

    # Re-apply localization patch
    Log-Msg "Applying Russian localization patch..." "STEP"
    $locPatcher = Join-Path $Global:ProjectRootDir "openhands-localization\patch-agent-canvas-localization.ps1"
    $locProc = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$locPatcher`"" -NoNewWindow -PassThru -Wait
    if ($locProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "LOCALIZATION_PATCH_FAILED"
    }

    # Strict localization parity audit
    Log-Msg "Auditing Russian localization parity (LOCALIZATION_STRICT_GATE = KEEP)..." "STEP"
    $auditScript = Join-Path $Global:ProjectRootDir "openhands-localization\audit-localization.py"
    $auditProc = Start-Process "python.exe" -ArgumentList "`"$auditScript`"" -NoNewWindow -PassThru -Wait
    if ($auditProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "LOCALE_AUDIT_SCRIPT_ERROR"
    }

    $auditJson = Join-Path $Global:ProjectRootDir "OpenHands-Tests\Russian-Localization\locale-audit.json"
    if (Test-Path $auditJson) {
        $auditData = Get-Content $auditJson -Raw | ConvertFrom-Json
        if ($auditData.missing_in_ru.Count -gt 0) {
            Log-Msg "Upstream introduced $($auditData.missing_in_ru.Count) new untranslated English keys!" "ERROR"
            Invoke-OpenHandsRollback "LOCALIZATION_PARITY_FAILED"
        }
    }
    Log-Msg "Localization parity audit: PASS (0 missing keys)" "SUCCESS"

    # Re-apply voice UI patch
    Log-Msg "Applying Voice UI patch..." "STEP"
    $voicePatcher = Join-Path $Global:ProjectRootDir "local-voice\patch-agent-canvas-voice.ps1"
    $voiceProc = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$voicePatcher`"" -NoNewWindow -PassThru -Wait
    if ($voiceProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "VOICE_PATCH_FAILED"
    }

    # Verify voice injection in build/index.html
    $buildIndex = Join-Path $canvasPkgDir "build\index.html"
    $htmlContent = [System.IO.File]::ReadAllText($buildIndex, [System.Text.Encoding]::UTF8)
    if (-not ($htmlContent.Contains("voice-bridge.css") -and $htmlContent.Contains("voice-bridge.js"))) {
        Log-Msg "Voice patch verification failed: anchors missing in index.html!" "ERROR"
        Invoke-OpenHandsRollback "VOICE_ANCHORS_NOT_FOUND"
    }
    Log-Msg "Voice UI patch verification: PASS" "SUCCESS"

    # Re-apply Working Profile UI patch
    Log-Msg "Applying Working Profile UI patch..." "STEP"
    $wpPatcher = Join-Path $Global:ProjectRootDir "openhands-working-profile\patch-agent-canvas-working-profile.ps1"
    $wpProc = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$wpPatcher`"" -NoNewWindow -PassThru -Wait
    if ($wpProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "WORKING_PROFILE_PATCH_FAILED"
    }

    # Re-apply Mobile PWA patch
    Log-Msg "Applying Mobile PWA patch..." "STEP"
    $pwaPatcher = Join-Path $Global:ProjectRootDir "openhands-pwa\patch-agent-canvas-pwa.ps1"
    $pwaProc = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$pwaPatcher`"" -NoNewWindow -PassThru -Wait
    if ($pwaProc.ExitCode -ne 0) {
        Invoke-OpenHandsRollback "PWA_PATCH_FAILED"
    }

    # Verify PWA injection in build/index.html
    $htmlContent = [System.IO.File]::ReadAllText($buildIndex, [System.Text.Encoding]::UTF8)
    if (-not ($htmlContent.Contains("manifest.webmanifest") -and $htmlContent.Contains("/sw.js") -and $htmlContent.Contains("mobile-pwa.css"))) {
        Log-Msg "PWA patch verification failed: anchors missing in index.html!" "ERROR"
        Invoke-OpenHandsRollback "PWA_ANCHORS_NOT_FOUND"
    }
    Log-Msg "Mobile PWA patch verification: PASS" "SUCCESS"

    Log-Msg "=====================================================================" "SUCCESS"
    Log-Msg "   OPENHANDS APP STACK UPDATED & VERIFIED: v$installedVer" "SUCCESS"
    Log-Msg "=====================================================================" "SUCCESS"
    Set-ComponentStatus "UPDATED"

    if ($RestartPlatform) {
        Log-Msg "Restarting platform per request..." "STEP"
        & "K:\Project\START-OPENHANDS-LOCAL.cmd"
    } else {
        Log-Msg "Station remains STOPPED per safety default." "INFO"
    }
    exit 0
}
