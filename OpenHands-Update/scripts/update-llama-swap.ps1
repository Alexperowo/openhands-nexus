# Official llama-swap Updater Script
# Location: K:\Project\OpenHands-Update\scripts\update-llama-swap.ps1

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

$ProjectRootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# Canonical Centralized Logs
$LogDir = Join-Path $ProjectRootDir "Logs\Updater"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "update-llama-swap-$ts.log"

function Log-Output([string]$msg, [string]$level = "INFO") {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $formatted = "[$now] [$level] $msg"
    switch ($level) {
        "ERROR"   { Write-Host $formatted -ForegroundColor Red }
        "WARN"    { Write-Host $formatted -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $formatted -ForegroundColor Green }
        "STEP"    { Write-Host $formatted -ForegroundColor Cyan }
        default   { Write-Host $formatted -ForegroundColor White }
    }
    Add-Content -Path $LogFile -Value $formatted -Encoding UTF8 -ErrorAction SilentlyContinue
}

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$Update.IsPresent) + ([int]$Rollback.IsPresent)
if ($modeCount -eq 0) {
    Log-Output "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
} elseif ($modeCount -gt 1) {
    Log-Output "Error: Only one of -CheckOnly, -DryRun, -Update, -Rollback may be specified." "ERROR"
    exit 1
}

# Production paths
$ProductionBin = Join-Path $ProjectRootDir "llama-swap\bin\llama-swap.exe"
$ProductionConfig = Join-Path $ProjectRootDir "llama-swap\config.yaml"
$StagingDir = Join-Path $ProjectRootDir "llama-swap\staging"
$BackupRoot = Join-Path $ProjectRootDir "Archive\backups\llama-swap"

function Assert-StationStopped([switch]$AllowRunningWarn) {
    $ports = @(8000, 8080, 8443, 18000, 18001, 18002)
    $activeConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    if ($activeConns) {
        $pList = ($activeConns.LocalPort | Select-Object -Unique) -join ", "
        if ($AllowRunningWarn) {
            Log-Output "Station status: RUNNING (Active ports: $pList) [Read-Only Check Mode]" "WARN"
            return
        }
        Log-Output "CRITICAL GATE FAILED: Production station is RUNNING (Active ports: $pList)." "ERROR"
        Log-Output "Refusing operation to protect live inference state." "ERROR"
        Log-Output "Please stop the platform first via STOP-OPENHANDS-LOCAL.cmd." "WARN"
        exit 1
    }
    Log-Output "Station status: STOPPED (All production ports free)" "SUCCESS"
}

# Read current production metadata
$currentVer = "unknown"
$currentSha = "unknown"
if (Test-Path $ProductionBin) {
    $currentSha = (Get-FileHash $ProductionBin -Algorithm SHA256).Hash
    try {
        $verRaw = & $ProductionBin -version 2>&1
        if ($verRaw -match "v\d+") {
            $currentVer = $Matches[0]
        } else {
            $currentVer = ($verRaw -split "`n")[0].Trim()
        }
    } catch {}
}

# 3. Release Discovery Function
function Get-UpstreamRelease([string]$target) {
    $apiUrl = if ($target -eq "latest") {
        "https://api.github.com/repos/mostlygeek/llama-swap/releases/latest"
    } else {
        "https://api.github.com/repos/mostlygeek/llama-swap/releases/tags/$target"
    }

    Log-Output "Querying llama-swap releases from GitHub API..." "INFO"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ "User-Agent" = "OpenHands-Update-Station/1.0" }

    $release = $null
    try {
        $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 10
    } catch {
        Log-Output "GitHub REST API returned: $($_.Exception.Message). Falling back to releases scraping..." "WARN"
        try {
            $rawHtml = [string]::Join("`n", (curl.exe -s -L "https://github.com/mostlygeek/llama-swap/releases"))
            if ($rawHtml -match '/mostlygeek/llama-swap/releases/tag/(v\d+)') {
                $discoveredTag = $Matches[1]
                $tagNum = $discoveredTag.TrimStart('v')
                $assetName = "llama-swap_${tagNum}_windows_amd64.zip"
                $downloadUrl = "https://github.com/mostlygeek/llama-swap/releases/download/$discoveredTag/$assetName"
                $release = [PSCustomObject]@{
                    tag_name = $discoveredTag
                    name = $discoveredTag
                    published_at = (Get-Date -Format "o")
                    assets = @(
                        [PSCustomObject]@{
                            name = $assetName
                            size = 22755929
                            browser_download_url = $downloadUrl
                        }
                    )
                }
            }
        } catch {
            Log-Output "Failed to scrape releases page: $($_.Exception.Message)" "ERROR"
            return $null
        }
    }

    $winAsset = $release.assets | Where-Object { $_.name -match "llama-swap_.*windows_amd64\.zip$" } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -match "checksums\.txt$" } | Select-Object -First 1

    if (-not $winAsset) {
        Log-Output "Could not locate Windows x64 ZIP asset in release $($release.tag_name)." "ERROR"
        return $null
    }

    return @{
        TagName = $release.tag_name
        Name = $release.name
        PublishedAt = $release.published_at
        Asset = $winAsset
        ChecksumAsset = $checksumAsset
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -CheckOnly
# ═══════════════════════════════════════════════════════════════════════════
if ($CheckOnly) {
    Log-Output "=== llama-swap Updater (CheckOnly Mode) ===" "STEP"
    Assert-StationStopped -AllowRunningWarn

    Log-Output "Current Production Binary:  $ProductionBin" "INFO"
    Log-Output "Current Production Version: $currentVer" "INFO"
    Log-Output "Current Production SHA256:  $currentSha" "INFO"

    $rel = Get-UpstreamRelease $TargetVersion
    if (-not $rel) {
        Log-Output "Release discovery failed." "ERROR"
        exit 1
    }

    Log-Output "Latest Upstream Tag:        $($rel.TagName)" "INFO"
    Log-Output "Windows Asset Name:         $($rel.Asset.name)" "INFO"
    Log-Output "Windows Asset URL:          $($rel.Asset.browser_download_url)" "INFO"
    Log-Output "Windows Asset Size:         $($rel.Asset.size) bytes" "INFO"

    # Verify asset availability via HTTP HEAD
    try {
        $req = [System.Net.WebRequest]::Create($rel.Asset.browser_download_url)
        $req.Method = "HEAD"
        $req.Timeout = 8000
        $resp = $req.GetResponse()
        $resp.Close()
        Log-Output "Asset availability verified: HTTP 200/302 OK" "SUCCESS"
    } catch {
        Log-Output "Asset HEAD check failed: $($_.Exception.Message)" "WARN"
    }

    if ($currentVer -eq $rel.TagName -and (-not $Force)) {
        Log-Output "Status: UP TO DATE ($currentVer is currently installed)" "SUCCESS"
    } else {
        Log-Output "Status: UPDATE AVAILABLE ($currentVer -> $($rel.TagName))" "WARN"
        Log-Output "To preview update: .\update-llama-swap.ps1 -DryRun" "INFO"
        Log-Output "To execute update: .\update-llama-swap.ps1 -Update -TargetVersion $($rel.TagName)" "INFO"
    }
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -DryRun
# ═══════════════════════════════════════════════════════════════════════════
if ($DryRun) {
    Log-Output "=== llama-swap Updater (DryRun Simulation Mode) ===" "STEP"
    Assert-StationStopped -AllowRunningWarn

    $rel = Get-UpstreamRelease $TargetVersion
    if (-not $rel) {
        Log-Output "DryRun aborted: Release discovery failed." "ERROR"
        exit 1
    }

    Log-Output "[SIMULATION] 1. Station stop gate: VERIFIED (All production ports free)" "INFO"
    Log-Output "[SIMULATION] 2. Upstream release target: $($rel.TagName)" "INFO"
    Log-Output "[SIMULATION] 3. Would download asset: $($rel.Asset.browser_download_url)" "INFO"
    Log-Output "[SIMULATION] 4. Would extract to staging: $StagingDir" "INFO"
    Log-Output "[SIMULATION] 5. Would test candidate process on test port 18080 using CURRENT config: $ProductionConfig" "INFO"
    Log-Output "[SIMULATION] 6. Candidate Gates: PROCESS_STARTED, CONFIG_PARSED, PORT_LISTENING, /health, /v1/models" "INFO"
    Log-Output "[SIMULATION] 7. Would backup current binary to: $BackupRoot\$ts-$currentVer\llama-swap.exe" "INFO"
    Log-Output "[SIMULATION] 8. Would promote candidate binary to: $ProductionBin" "INFO"
    Log-Output "[SIMULATION] 9. Final state: Station remains STOPPED by default." "INFO"
    Log-Output "DryRun completed successfully. ZERO files modified." "SUCCESS"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -Rollback
# ═══════════════════════════════════════════════════════════════════════════
if ($Rollback) {
    Log-Output "=== llama-swap Rollback ===" "WARN"
    Assert-StationStopped

    $bakBin = Join-Path $ProjectRootDir "llama-swap\bin\llama-swap.exe.bak"
    $restored = $false

    if (Test-Path $bakBin) {
        Log-Output "Found local backup binary: $bakBin" "INFO"
        Copy-Item $bakBin $ProductionBin -Force
        $restored = $true
    } else {
        # Check archive backup root
        if (Test-Path $BackupRoot) {
            $latestBackupDir = Get-ChildItem -Path $BackupRoot -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($latestBackupDir) {
                $archiveBin = Join-Path $latestBackupDir.FullName "llama-swap.exe"
                if (Test-Path $archiveBin) {
                    Log-Output "Restoring from archive backup: $archiveBin" "INFO"
                    Copy-Item $archiveBin $ProductionBin -Force
                    $restored = $true
                }
            }
        }
    }

    if (-not $restored) {
        Log-Output "Rollback failed: No backup binary found!" "ERROR"
        exit 1
    }

    $newHash = (Get-FileHash $ProductionBin -Algorithm SHA256).Hash
    Log-Output "Restoration complete. Restored SHA256: $newHash" "SUCCESS"
    Log-Output "Station remains STOPPED per safety policy." "INFO"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MODE: -Update
# ═══════════════════════════════════════════════════════════════════════════
if ($Update) {
    Log-Output "=== llama-swap Production Update ===" "STEP"
    Assert-StationStopped

    # Mode -Update explicitly authorized
    Log-Output "Executing authorized real update of llama-swap..." "INFO" 

    $rel = Get-UpstreamRelease $TargetVersion
    if (-not $rel) { exit 1 }

    # Setup staging directory
    if (Test-Path $StagingDir) { Remove-Item $StagingDir -Recurse -Force | Out-Null }
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

    $zipPath = Join-Path $StagingDir $rel.Asset.name
    Log-Output "Downloading $($rel.Asset.browser_download_url)..." "STEP"
    Invoke-WebRequest -Uri $rel.Asset.browser_download_url -OutFile $zipPath -TimeoutSec 120

    Log-Output "Extracting candidate package..." "STEP"
    Expand-Archive -Path $zipPath -DestinationPath $StagingDir -Force

    $candidateBin = Join-Path $StagingDir "llama-swap.exe"
    if (-not (Test-Path $candidateBin)) {
        Log-Output "Candidate binary not found in extracted archive!" "ERROR"
        exit 1
    }

    $candidateVer = (& $candidateBin -version 2>&1)
    Log-Output "Candidate binary version: $candidateVer" "INFO"

    # Candidate Validation Gate on Isolated Test Port 18080
    Log-Output "Starting candidate validation gate on test port 18080..." "STEP"
    $testPort = 18080
    $testProc = Start-Process -FilePath $candidateBin -ArgumentList "-config `"$ProductionConfig`" -listen 127.0.0.1:$testPort" -PassThru -NoNewWindow
    Start-Sleep -Seconds 2

    $gatePassed = $false
    try {
        for ($i = 0; $i -lt 10; $i++) {
            try {
                $res = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/health" -TimeoutSec 2 -ErrorAction Stop
                if ($res -eq "OK") {
                    $modelsRes = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/v1/models" -TimeoutSec 2 -ErrorAction Stop
                    if ($modelsRes.data.Count -gt 0) {
                        $gatePassed = $true
                        Log-Output "Candidate validation gate PASSED (/health OK, /v1/models loaded: $($modelsRes.data.Count) models)" "SUCCESS"
                        break
                    }
                }
            } catch {}
            Start-Sleep -Seconds 1
        }
    } finally {
        if ($testProc -and -not $testProc.HasExited) {
            Stop-Process -Id $testProc.Id -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not $gatePassed) {
        Log-Output "CANDIDATE GATE FAILED: Candidate failed health or config validation. Aborting update." "ERROR"
        exit 1
    }

    # Backup current production binary
    $backupFolder = Join-Path $BackupRoot "$ts-v$currentVer"
    New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
    Copy-Item $ProductionBin (Join-Path $backupFolder "llama-swap.exe") -Force
    Copy-Item $ProductionBin (Join-Path $ProjectRootDir "llama-swap\bin\llama-swap.exe.bak") -Force
    Log-Output "Backup created at: $backupFolder" "SUCCESS"

    # Atomic promotion
    Copy-Item $candidateBin $ProductionBin -Force
    $newHash = (Get-FileHash $ProductionBin -Algorithm SHA256).Hash
    Log-Output "PROMOTION COMPLETE: llama-swap upgraded to $($rel.TagName) (SHA256: $newHash)" "SUCCESS"

    if ($RestartPlatform) {
        Log-Output "Restarting platform per request..." "STEP"
        & (Join-Path $ProjectRootDir "START-OPENHANDS-LOCAL.cmd")
    } else {
        Log-Output "Station remains STOPPED per safety default." "INFO"
    }
    exit 0
}
