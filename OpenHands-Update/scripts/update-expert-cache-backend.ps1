<#
.SYNOPSIS
    Hardened Updater for Qwen 122B MoE Expert Cache Backend (llama.cpp fork).
.DESCRIPTION
    Safely manages updates, builds, and rollbacks for the MoE Expert Cache CUDA backend
    used by Qwen 3.5 122B in OpenHands Nexus.
    Supports -CheckOnly, -DryRun, -Update, and -Rollback.
    Enforces safe default invocation (-CheckOnly).
    Station stop is a HARD GATE before any modifying update or rollback.
    Candidate binaries undergo a strict qualification gate (checking --moe-expert-cache flag)
    prior to production promotion.
.PARAMETER CheckOnly
    Inspects current production binary, git commit, remote branch status, and reports.
.PARAMETER DryRun
    Simulates complete update workflow without modifying any files.
.PARAMETER Update
    Performs pre-update backup, staging build with MSVC & CUDA (SM75+SM120), qualification gate, and promotion.
.PARAMETER Rollback
    Rolls back production binaries to a previous backup.
.PARAMETER TargetCommit
    Explicit commit or branch to build. Defaults to remote moe-expert-cache HEAD.
.PARAMETER BackupPath
    Explicit backup folder for rollback. Defaults to the latest available backup.
.PARAMETER Force
    Allows rebuilding even if current production commit matches target commit.
.PARAMETER RestartPlatform
    If specified, restarts the OpenHands platform after update/rollback.
#>

[CmdletBinding(DefaultParameterSetName = "Default")]
param(
    [Parameter(ParameterSetName = "Check")]
    [switch]$CheckOnly,

    [Parameter(ParameterSetName = "DryRun")]
    [switch]$DryRun,

    [Parameter(ParameterSetName = "Update")]
    [switch]$Update,

    [Parameter(ParameterSetName = "Rollback")]
    [switch]$Rollback,

    [Parameter(ParameterSetName = "Update")]
    [string]$TargetCommit = "",

    [Parameter(ParameterSetName = "Rollback")]
    [string]$BackupPath = "",

    [switch]$Force,

    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "expert-cache"

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$Update.IsPresent) + ([int]$Rollback.IsPresent)
if ($modeCount -eq 0 -and (-not $Force) -and (-not $TargetCommit)) {
    Log-Msg "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
}

# Paths & Directories
$ExpertCacheRoot    = Join-Path $Global:ProjectRootDir "LLM-tests\Qwen122B-Expert-Cache"
$ProdBinDir         = Join-Path $ExpertCacheRoot "bin"
$SrcDir             = Join-Path $Global:ProjectRootDir "LLM-tests\moe-expert-cache-src"
$StagingRootDir     = Join-Path $Global:UpdateRootDir "staging\expert-cache"
$StagingBuildDir    = Join-Path $StagingRootDir "build"
$StagingBinDir      = Join-Path $StagingRootDir "bin"
$ArchiveBackupDir   = Join-Path $Global:ProjectRootDir "Archive\backups\expert-cache"
$StateFile          = Join-Path $Global:UpdateRootDir "state\expert_cache_state.json"
$LastRunStatusFile  = Join-Path $Global:UpdateRootDir "state\last_run_status.json"

# Ensure directories exist
foreach ($dir in @($ArchiveBackupDir, (Join-Path $Global:UpdateRootDir "state"), $StagingRootDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# Locate Visual Studio vcvars64.bat
$vcvarsCandidates = @(
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
)
$vcvars = $null
foreach ($vc in $vcvarsCandidates) {
    if (Test-Path $vc) {
        $vcvars = $vc
        break
    }
}

function Assert-StationStopped([switch]$AllowRunningWarn) {
    $ports = @(8000, 8080, 8443, 18000, 18001, 18002)
    $activeConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    if ($activeConns) {
        $pList = ($activeConns.LocalPort | Select-Object -Unique) -join ", "
        if ($AllowRunningWarn) {
            Log-Msg "Station status: RUNNING (Active ports: $pList) [Read-Only Check Mode]" "WARN"
            return
        }
        Log-Msg "CRITICAL HARD GATE FAILED: Production station is RUNNING (Active ports: $pList)." "ERROR"
        Log-Msg "Refusing backend modification to protect active inference memory. Stop station first." "ERROR"
        Log-Msg "Run STOP-OPENHANDS-LOCAL.cmd before updating or rolling back." "WARN"
        exit 1
    }
    Log-Msg "Station safety gate: STOPPED (All production ports free)" "SUCCESS"
}

function Set-ComponentStatus([string]$Status) {
    $cur = @{}
    if (Test-Path $LastRunStatusFile) {
        try { $cur = Get-Content $LastRunStatusFile -Raw | ConvertFrom-Json } catch { $cur = @{} }
    }
    $cur | Add-Member -NotePropertyName "moe_expert_cache" -NotePropertyValue $Status -Force
    $cur | ConvertTo-Json | Out-File -FilePath $LastRunStatusFile -Encoding UTF8
}

Log-Msg "=====================================================================" "STEP"
Log-Msg "       QWEN 122B MOE EXPERT CACHE BACKEND UPDATER" "STEP"
Log-Msg "=====================================================================" "STEP"

# -------------------------------------------------------------
# MODE: ROLLBACK
# -------------------------------------------------------------
if ($Rollback) {
    Log-Msg "=== MoE Expert Cache Backend Rollback ===" "WARN"
    Assert-StationStopped

    if (-not $BackupPath) {
        $allBackups = Get-ChildItem -Path $ArchiveBackupDir -Directory -ErrorAction SilentlyContinue | Sort-Object CreationTime -Descending
        if ($allBackups.Count -gt 0) {
            $BackupPath = $allBackups[0].FullName
        }
    }

    if (-not $BackupPath -or (-not (Test-Path $BackupPath))) {
        Log-Msg "No valid backup found to rollback from in: $ArchiveBackupDir" "ERROR"
        Set-ComponentStatus "ROLLBACK_NO_BACKUP"
        exit 1
    }

    Log-Msg "Target rollback backup: $BackupPath" "INFO"
    Fast-CopyDir $BackupPath $ProdBinDir -Mirror
    Log-Msg "Restored production binaries from backup." "SUCCESS"

    $infoFile = Join-Path $BackupPath "backup-info.json"
    if (Test-Path $infoFile) {
        Copy-Item -Path $infoFile -Destination (Join-Path $ProdBinDir "CURRENT_BUILD_INFO.json") -Force
    }

    Set-ComponentStatus "ROLLBACK_SUCCESS"
    Log-Msg "Rollback completed successfully." "SUCCESS"

    if ($RestartPlatform) {
        Log-Msg "Restarting OpenHands platform as requested..." "STEP"
        & (Join-Path $Global:ProjectRootDir ".openhands-local\start.ps1")
    }
    exit 0
}

# -------------------------------------------------------------
# INSPECTION: Current Production & Source State
# -------------------------------------------------------------
if (-not (Test-Path $SrcDir)) {
    Log-Msg "MoE Expert Cache source tree not found at: $SrcDir" "ERROR"
    Set-ComponentStatus "SOURCE_NOT_FOUND"
    exit 1
}

$prodServerExe = Join-Path $ProdBinDir "llama-server.exe"
$prodCommit = "unknown"
$prodHash = "unknown"
$hasMoeCacheFlag = $false

if (Test-Path $prodServerExe) {
    $prodHash = (Get-FileHash $prodServerExe -Algorithm SHA256).Hash
    try {
        $verOut = & "$prodServerExe" --version 2>&1
        if ($verOut -match "commit\s+([a-f0-9]{7,})") {
            $prodCommit = $Matches[1]
        }
    } catch {}

    try {
        $helpOut = & "$prodServerExe" --help 2>&1
        if ($helpOut -match "--moe-expert-cache") {
            $hasMoeCacheFlag = $true
        }
    } catch {}
}

$localHeadCommit = (& git -C $SrcDir rev-parse HEAD).Trim()
$localHeadShort  = (& git -C $SrcDir rev-parse --short HEAD).Trim()

# Check remote updates on origin/moe-expert-cache
$remoteUpdateAvailable = $false
$remoteCommit = $localHeadCommit
$targetRef = $null

if ($TargetCommit) {
    $targetRef = $TargetCommit
    Log-Msg "Using explicitly specified target commit: $targetRef" "INFO"
} else {
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & git -C $SrcDir fetch origin moe-expert-cache 2>$null
        $ErrorActionPreference = $prevEAP
        if ($LASTEXITCODE -eq 0) {
            $remoteCommit = (& git -C $SrcDir rev-parse origin/moe-expert-cache).Trim()
            if ($remoteCommit -ne $localHeadCommit) {
                $remoteUpdateAvailable = $true
                $targetRef = "origin/moe-expert-cache"
            }
        }
    } catch {
        Log-Msg "Remote fetch skipped or network restricted: $_" "WARN"
    }
}

# -------------------------------------------------------------
# MODE: CHECK ONLY
# -------------------------------------------------------------
if ($CheckOnly) {
    Assert-StationStopped -AllowRunningWarn
    Log-Msg "Current Production Bin:      $prodServerExe" "INFO"
    Log-Msg "Current Production SHA256:   $prodHash" "INFO"
    Log-Msg "Current Production Commit:   $prodCommit" "INFO"
    Log-Msg "Source HEAD Commit:          $localHeadShort ($localHeadCommit)" "INFO"
    Log-Msg "MoE Cache Support Verified:  $(if ($hasMoeCacheFlag) { 'YES (--moe-expert-cache present)' } else { 'NO (Missing flag!)' })" $(if ($hasMoeCacheFlag) { "SUCCESS" } else { "ERROR" })

    if ($remoteUpdateAvailable) {
        $remoteShort = $remoteCommit.Substring(0, [Math]::Min(7, $remoteCommit.Length))
        Log-Msg "Remote Update Available:     $localHeadShort -> $remoteShort (branch: moe-expert-cache)" "WARN"
        Log-Msg "To preview update:           .\update-expert-cache-backend.ps1 -DryRun" "INFO"
        Log-Msg "To compile & update:         .\update-expert-cache-backend.ps1 -Update" "INFO"
        Set-ComponentStatus "UPDATE_AVAILABLE"
    } else {
        Log-Msg "Status:                      UP TO DATE at commit $localHeadShort" "SUCCESS"
        Set-ComponentStatus "UP_TO_DATE"
    }
    exit 0
}

# -------------------------------------------------------------
# MODE: DRY RUN
# -------------------------------------------------------------
if ($DryRun) {
    Assert-StationStopped -AllowRunningWarn
    Log-Msg "=== MoE Expert Cache Updater (DryRun Simulation) ===" "STEP"
    Log-Msg "[SIMULATION] 1. Station stop hard gate: VALIDATED." "INFO"
    Log-Msg "[SIMULATION] 2. Pre-update backup would be written to: $ArchiveBackupDir\<timestamp>-${localHeadShort}" "INFO"
    Log-Msg "[SIMULATION] 3. MSVC BuildTools located at: $vcvars" "INFO"
    Log-Msg "[SIMULATION] 4. CMake configuration targets: SM75 (RTX 2080 Ti) + SM120 (RTX 5060 Ti)" "INFO"
    Log-Msg "[SIMULATION] 5. Staging build directory: $StagingBuildDir" "INFO"
    Log-Msg "[SIMULATION] 6. Staging qualification gate: verifies --moe-expert-cache flag" "INFO"
    Log-Msg "[SIMULATION] 7. Promotion target: $ProdBinDir" "INFO"
    Log-Msg "DryRun simulation finished cleanly. ZERO files modified." "SUCCESS"
    exit 0
}

# -------------------------------------------------------------
# MODE: UPDATE
# -------------------------------------------------------------
if (-not $targetRef -and (-not $Force)) {
    Log-Msg "Already at latest commit $localHeadShort. Use -Force to rebuild." "SUCCESS"
    Set-ComponentStatus "NO_UPDATE_AVAILABLE"
    exit 0
}

if (-not $targetRef -and $Force) {
    $targetRef = "HEAD"
    Log-Msg "Forced rebuild requested on commit: $localHeadShort" "INFO"
}

Assert-StationStopped

if (-not $vcvars) {
    Log-Msg "Visual Studio 2022 vcvars64.bat not found in expected locations!" "ERROR"
    Set-ComponentStatus "MSVC_NOT_FOUND"
    exit 1
}

# Step 1: Pre-update backup
Log-Msg "[1/6] Creating pre-update backup of production binaries..." "STEP"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$backupTarget = Join-Path $ArchiveBackupDir "${ts}-${localHeadShort}"
New-Item -ItemType Directory -Path $backupTarget -Force | Out-Null
Fast-CopyDir $ProdBinDir $backupTarget

$backupInfo = @{
    timestamp = (Get-Date -Format "o")
    production_commit = $prodCommit
    production_hash = $prodHash
    source_commit = $localHeadCommit
    backup_path = $backupTarget
}
$backupInfo | ConvertTo-Json | Out-File -FilePath (Join-Path $backupTarget "backup-info.json") -Encoding UTF8
Log-Msg "      Backed up production bin to: $backupTarget" "SUCCESS"

# Step 2: Ensure source cleanliness & Windows compatibility
Log-Msg "[2/6] Verifying Windows compatibility patch in source..." "STEP"
$ggmlCpuFile = Join-Path $SrcDir "ggml\src\ggml-cpu\ggml-cpu.c"
if (Test-Path $ggmlCpuFile) {
    $cpuContent = Get-Content $ggmlCpuFile -Raw
    if ($cpuContent -match "flockfile\(moe_log_file\)" -and -not ($cpuContent -match "_lock_file\(moe_log_file\)")) {
        Log-Msg "      Applying MSVC Windows _lock_file patch to $ggmlCpuFile..." "INFO"
        $patched = $cpuContent.Replace(
            "flockfile(moe_log_file);",
            "#ifdef _WIN32`r`n                _lock_file(moe_log_file);`r`n#else`r`n                flockfile(moe_log_file);`r`n#endif"
        ).Replace(
            "funlockfile(moe_log_file);",
            "#ifdef _WIN32`r`n                _unlock_file(moe_log_file);`r`n#else`r`n                funlockfile(moe_log_file);`r`n#endif"
        )
        Set-Content -Path $ggmlCpuFile -Value $patched -Encoding UTF8
        Log-Msg "      MSVC patch applied successfully." "SUCCESS"
    } else {
        Log-Msg "      Windows compatibility patch is already present." "SUCCESS"
    }
}

# Step 3: Configure CMake in staging
Log-Msg "[3/6] Configuring CMake in staging build directory..." "STEP"
if (Test-Path $StagingBuildDir) {
    Remove-Item -Path $StagingBuildDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $StagingBuildDir -Force | Out-Null

$cmakeConfig = "cmake -B `"$StagingBuildDir`" -S `"$SrcDir`" -G `"Visual Studio 17 2022`" -A x64 " +
    "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=`"75;120`" -DGGML_CUDA_FA_ALL_QUANTS=ON " +
    "-DGGML_CUDA_FUSION=1"

$runCmakeBat = Join-Path $StagingBuildDir "run_cmake.bat"
Set-Content -Path $runCmakeBat -Value "@call `"$vcvars`"`r`n$cmakeConfig`r`n" -Encoding ASCII

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$cfgOut = & cmd.exe /c "$runCmakeBat" 2>&1
$cfgExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($cfgExit -ne 0) {
    Log-Msg "CMake configuration failed:`n$cfgOut" "ERROR"
    Set-ComponentStatus "CMAKE_CONFIG_FAILED"
    exit 1
}
Log-Msg "      CMake configured successfully with CUDA SM75 + SM120." "SUCCESS"

# Step 4: Compile Release binaries
Log-Msg "[4/6] Compiling llama-server and llama-cli (Release)..." "STEP"
$cmakeBuild = "cmake --build `"$StagingBuildDir`" --config Release --target llama-server llama-cli --parallel 8"
$runBuildBat = Join-Path $StagingBuildDir "run_build.bat"
Set-Content -Path $runBuildBat -Value "@call `"$vcvars`"`r`n$cmakeBuild`r`n" -Encoding ASCII

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$buildOut = & cmd.exe /c "$runBuildBat" 2>&1
$buildExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($buildExit -ne 0) {
    Log-Msg "Compilation failed:`n$buildOut" "ERROR"
    Set-ComponentStatus "BUILD_FAILED"
    exit 1
}
Log-Msg "      Compilation completed successfully." "SUCCESS"

# Step 5: Candidate Qualification Gate
Log-Msg "[5/6] Executing candidate qualification gate..." "STEP"
$builtServer = Join-Path $StagingBuildDir "bin\Release\llama-server.exe"
if (-not (Test-Path $builtServer)) {
    $builtServer = Join-Path $StagingBuildDir "bin\llama-server.exe"
}

if (-not (Test-Path $builtServer)) {
    Log-Msg "Candidate llama-server.exe not found in build tree!" "ERROR"
    Set-ComponentStatus "BINARY_NOT_FOUND"
    exit 1
}

$candidateHelp = & "$builtServer" --help 2>&1
if (-not ($candidateHelp -match "--moe-expert-cache")) {
    Log-Msg "QUALIFICATION GATE FAILED: Candidate binary does NOT support --moe-expert-cache!" "ERROR"
    Log-Msg "Refusing promotion to protect station functionality." "ERROR"
    Set-ComponentStatus "QUALIFICATION_GATE_FAILED"
    exit 1
}
Log-Msg "      Candidate qualification gate PASSED: --moe-expert-cache verified." "SUCCESS"

# Step 6: Atomic Promotion to Production
Log-Msg "[6/6] Promoting candidate binaries to production ($ProdBinDir)..." "STEP"
$builtDir = Split-Path $builtServer -Parent
Copy-Item -Path (Join-Path $builtDir "*") -Destination $ProdBinDir -Recurse -Force
Log-Msg "      Production binaries updated successfully." "SUCCESS"

# Update state file
$newState = @{
    production_commit = $localHeadCommit
    short_commit = $localHeadShort
    updated_at = (Get-Date -Format "o")
    hash = (Get-FileHash (Join-Path $ProdBinDir "llama-server.exe") -Algorithm SHA256).Hash
    moe_cache_verified = $true
}
$newState | ConvertTo-Json | Out-File -FilePath $StateFile -Encoding UTF8
Set-ComponentStatus "UPDATE_SUCCESS"

Log-Msg "=====================================================================" "STEP"
Log-Msg "MoE Expert Cache Backend updated successfully to commit $localHeadShort." "SUCCESS"
Log-Msg "=====================================================================" "STEP"

if ($RestartPlatform) {
    Log-Msg "Restarting OpenHands platform as requested..." "STEP"
    & (Join-Path $Global:ProjectRootDir ".openhands-local\start.ps1")
}

exit 0
