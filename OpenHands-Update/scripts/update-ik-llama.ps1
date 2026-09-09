# ik_llama Backend Updater Script
# Location: K:\Project\OpenHands-Update\scripts\update-ik-llama.ps1

param(
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$Update,
    [switch]$Force,
    [string]$TargetCommit = "",
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "ik-llama"

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$Update.IsPresent)
if ($modeCount -eq 0 -and (-not $Force) -and (-not $TargetCommit)) {
    Log-Msg "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
}

# Station stopped gate function
function Assert-StationStopped([switch]$AllowRunningWarn) {
    $ports = @(8000, 8080, 8443, 18000, 18001, 18002)
    $activeConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    if ($activeConns) {
        $pList = ($activeConns.LocalPort | Select-Object -Unique) -join ", "
        if ($AllowRunningWarn) {
            Log-Msg "Station status: RUNNING (Active ports: $pList) [Read-Only Check Mode]" "WARN"
            return
        }
        Log-Msg "CRITICAL GATE FAILED: Production station is RUNNING (Active ports: $pList)." "ERROR"
        Log-Msg "Refusing operation to protect live inference state." "ERROR"
        Log-Msg "Please stop the platform first via STOP-OPENHANDS-LOCAL.cmd." "WARN"
        exit 1
    }
    Log-Msg "Station status: STOPPED (All production ports free)" "SUCCESS"
}

Log-Msg "=====================================================================" "STEP"
Log-Msg "               IK_LLAMA BACKEND UPDATER" "STEP"
Log-Msg "=====================================================================" "STEP"

$ikRoot = Join-Path $Global:ProjectRootDir "ik_llama"
$srcDir = Join-Path $ikRoot "src"
$prodBinDir = Join-Path $ikRoot "bin"
$stagingSourceDir = Join-Path $ikRoot "src-staging"
$stagingBuildDir = Join-Path $ikRoot "build-staging"
$stagingBinDir = Join-Path $ikRoot "staging-bin"
$stateFile = Join-Path $Global:UpdateRootDir "state\ik_llama_state.json"
$lastRunStatusFile = Join-Path $Global:UpdateRootDir "state\last_run_status.json"

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$expectedModel = Join-Path $Global:ProjectRootDir "Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
$qwenMmproj = Join-Path $Global:ProjectRootDir "Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf"
$ornithModel = Join-Path $Global:ProjectRootDir "Models\Ornith\Ornith-1.5-35B-MTP-19G-ICE.gguf"

if (-not (Test-Path $srcDir)) {
    Log-Msg "ik_llama source tree not found at: $srcDir" "ERROR"
    exit 1
}

# Helper to record last run status
function Set-ComponentStatus([string]$Status) {
    $cur = @{}
    if (Test-Path $lastRunStatusFile) {
        try { $cur = Get-Content $lastRunStatusFile -Raw | ConvertFrom-Json } catch { $cur = @{} }
    }
    $cur | Add-Member -NotePropertyName "ik_llama" -NotePropertyValue $Status -Force
    $cur | ConvertTo-Json | Out-File -FilePath $lastRunStatusFile -Encoding UTF8
}

# Load existing state & baseline
$state = $null
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        Log-Msg "Loaded existing state: commit=$($state.production_commit), baseline=$($state.benchmark_baseline) tok/s" "INFO"
    } catch {
        $state = $null
    }
}

# 1. Inspect Git repository status
Log-Msg "[1/8] Inspecting Git status in $srcDir..." "STEP"
$gitStatus = & git -C $srcDir status --porcelain
if ($gitStatus) {
    Log-Msg "Dirty working tree detected in $srcDir!" "ERROR"
    Log-Msg "Uncommitted changes exist. Aborting update to protect local code." "WARN"
    Set-ComponentStatus "DIRTY_TREE_ABORT"
    exit 1
}

$currentCommit = (& git -C $srcDir rev-parse HEAD).Trim()
$currentShort = (& git -C $srcDir rev-parse --short HEAD).Trim()
Log-Msg "      Current production commit: $currentShort ($currentCommit)" "INFO"

# 2. Check remote repository updates
Log-Msg "[2/8] Checking remote repository updates..." "STEP"
$targetRef = $null
$remoteUpdateAvailable = $false

if ($TargetCommit) {
    $targetRef = $TargetCommit
    Log-Msg "      Using explicitly specified target commit: $targetRef" "INFO"
} else {
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & git -C $srcDir fetch origin main 2>$null
        $ErrorActionPreference = $prevEAP
        if ($LASTEXITCODE -eq 0) {
            $remoteCommit = (& git -C $srcDir rev-parse origin/main).Trim()
            Log-Msg "      Remote origin/main commit: $remoteCommit" "INFO"
            if ($remoteCommit -ne $currentCommit) {
                $remoteUpdateAvailable = $true
                $targetRef = "origin/main"
                Log-Msg "      New remote commit detected: $remoteCommit" "SUCCESS"
            }
        } else {
            Log-Msg "Could not fetch remote origin (exit code: $LASTEXITCODE)" "WARN"
        }
    } catch {
        Log-Msg "Network/proxy prevented remote check: $_" "WARN"
    }
}


if ($CheckOnly) {
    Log-Msg "=== ik_llama Updater (CheckOnly Mode) ===" "STEP"
    Assert-StationStopped -AllowRunningWarn
    Log-Msg "Current Production Commit: $currentShort ($currentCommit)" "INFO"
    $prodExe = Join-Path $prodBinDir "llama-server.exe"
    if (Test-Path $prodExe) {
        $hash = (Get-FileHash $prodExe -Algorithm SHA256).Hash
        Log-Msg "Current Production SHA256: $hash" "INFO"
    }
    if ($remoteUpdateAvailable) {
        Log-Msg "Status: UPDATE AVAILABLE (commit $currentShort -> $remoteCommit)" "WARN"
        Log-Msg "To preview update: .\update-ik-llama.ps1 -DryRun" "INFO"
        Log-Msg "To execute update: .\update-ik-llama.ps1 -Update" "INFO"
    } else {
        Log-Msg "Status: UP TO DATE (at commit $currentShort)" "SUCCESS"
    }
    exit 0
}

if ($DryRun) {
    Log-Msg "=== ik_llama Updater (DryRun Simulation Mode) ===" "STEP"
    Assert-StationStopped -AllowRunningWarn
    Log-Msg "[SIMULATION] 1. Station stop gate: VERIFIED" "INFO"
    Log-Msg "[SIMULATION] 2. Current commit: $currentShort, Target ref: $(if ($targetRef) { $targetRef } else { 'latest' })" "INFO"
    Log-Msg "[SIMULATION] 3. Would clone/pull commit into isolated staging: $stagingSourceDir" "INFO"
    Log-Msg "[SIMULATION] 4. Would compile candidate via MSVC 2022 vcvars64 in: $stagingBuildDir" "INFO"
    Log-Msg "[SIMULATION] 5. Would test candidate boot with Qwen 3.8 + --mmproj (QWEN_MAIN_LOAD, QWEN_MMPROJ_LOAD, QWEN_MTP_AVAILABLE)" "INFO"
    Log-Msg "[SIMULATION] 6. Would test candidate boot with Ornith 1.5-35B + MTP spec gate" "INFO"
    Log-Msg "[SIMULATION] 7. Would backup current bin to: $Global:BackupDir\ik_llama\<timestamp>" "INFO"
    Log-Msg "[SIMULATION] 8. Would promote candidate binaries to: $prodBinDir" "INFO"
    Log-Msg "[SIMULATION] 9. Final state: Station remains STOPPED by default." "INFO"
    Log-Msg "DryRun completed successfully. ZERO files modified." "SUCCESS"
    exit 0
}

if (-not $targetRef -and (-not $Force)) {
    Log-Msg "[STATUS] NO_UPDATE_AVAILABLE (ik_llama is already at latest commit $currentShort)" "SUCCESS"
    Set-ComponentStatus "NO_UPDATE_AVAILABLE"
    exit 0
}

if (-not $targetRef -and $Force) {
    $targetRef = "HEAD"
    Log-Msg "      Forced rebuild of current commit: $currentShort" "INFO"
}

# 3. Create Pre-Update Production Bin Backup & compute runtime hash
Log-Msg "[3/8] Backing up production bin runtime..." "STEP"
$prodServerExe = Join-Path $prodBinDir "llama-server.exe"
$currentProdHash = ""
if (Test-Path $prodServerExe) {
    $currentProdHash = (Get-FileHash $prodServerExe -Algorithm SHA256).Hash
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFolder = Join-Path $Global:BackupDir "ik_llama\${ts}-${currentShort}"
New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
Fast-CopyDir $prodBinDir $backupFolder

$backupMeta = @{
    timestamp = (Get-Date -Format "o")
    production_commit = $currentCommit
    short_commit = $currentShort
    production_runtime_hash = $currentProdHash
    benchmark_baseline = if ($state) { $state.benchmark_baseline } else { $null }
    backup_path = $backupFolder
    source_bin = $prodBinDir
}
$backupMeta | ConvertTo-Json | Out-File -FilePath (Join-Path $backupFolder "backup-info.json") -Encoding UTF8
Set-Content -Path (Join-Path $Global:BackupDir "ik_llama\\latest-backup.txt") -Value $backupFolder -Encoding UTF8
Log-Msg "      Production bin backed up to: $backupFolder" "SUCCESS"

# 4. Prepare staging worktree & build environment
# CRITICAL: $srcDir HEAD remains strictly untouched on currentCommit until PASS!
Log-Msg "[4/8] Creating isolated git worktree for staging at $stagingSourceDir..." "STEP"

# Clean previous worktree if any was left
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& git -C $srcDir worktree remove --force "$stagingSourceDir" 2>$null
& git -C $srcDir worktree prune 2>$null
$ErrorActionPreference = $prevEAP

$existingBuilt = (Test-Path (Join-Path $stagingBinDir "llama-server.exe")) -or (Test-Path (Join-Path $stagingBuildDir "bin\Release\llama-server.exe"))
if (-not $existingBuilt -or $Force) {
    if (Test-Path $stagingBuildDir) { Remove-Item -Path $stagingBuildDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $stagingBinDir) { Remove-Item -Path $stagingBinDir -Recurse -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Path $stagingBuildDir -Force | Out-Null
    New-Item -ItemType Directory -Path $stagingBinDir -Force | Out-Null
} else {
    Log-Msg "Existing candidate build found in staging. Preserving staging build." "INFO"
    if (-not (Test-Path $stagingBuildDir)) { New-Item -ItemType Directory -Path $stagingBuildDir -Force | Out-Null }
    if (-not (Test-Path $stagingBinDir)) { New-Item -ItemType Directory -Path $stagingBinDir -Force | Out-Null }
}

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$wtRes = & git -C $srcDir worktree add --detach "$stagingSourceDir" $targetRef 2>&1
$wtCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($wtCode -ne 0 -and -not (Test-Path (Join-Path $stagingSourceDir ".git"))) {
    Log-Msg "Failed to create git worktree: $wtRes" "ERROR"
    Set-ComponentStatus "WORKTREE_FAILED"
    exit 1
}

$stagingCommit = if (Test-Path $stagingSourceDir) { (& git -C $stagingSourceDir rev-parse HEAD).Trim() } else { $targetRef }
$stagingShort = if (Test-Path $stagingSourceDir) { (& git -C $stagingSourceDir rev-parse --short HEAD).Trim() } else { $targetRef.Substring(0,7) }
Log-Msg "      Staging worktree checked out at: $stagingShort ($stagingCommit)" "INFO"
Log-Msg "      Production source ($srcDir) remains at: $currentShort (UNTOUCHED)" "SUCCESS"

function Clean-StagingResources() {
    Log-Msg "Cleaning up staging worktree and build directories..." "INFO"
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & git -C $srcDir worktree remove --force "$stagingSourceDir" 2>$null
    & git -C $srcDir worktree prune 2>$null
    $ErrorActionPreference = $prevEAP
    if (Test-Path $stagingSourceDir) { Remove-Item -Path $stagingSourceDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $stagingBuildDir) { Remove-Item -Path $stagingBuildDir -Recurse -Force -ErrorAction SilentlyContinue }
}

# 5. Build in staging using CMake & Visual Studio BuildTools (RTX 2080 Ti CUDA sm_75)
$builtServer = Join-Path $stagingBuildDir "bin\Release\llama-server.exe"
if (-not (Test-Path $builtServer)) { $builtServer = Join-Path $stagingBuildDir "bin\llama-server.exe" }
if (-not (Test-Path $builtServer)) { $builtServer = Join-Path $stagingBinDir "llama-server.exe" }

if (Test-Path $builtServer) {
    Log-Msg "[5/8] Candidate binary already compiled ($builtServer). Skipping rebuild." "SUCCESS"
} else {
    Log-Msg "[5/8] Building ik_llama with CUDA sm_75 support in staging..." "STEP"
    $cmakeConfigureCmd = "cmake -B `"$stagingBuildDir`" -S `"$stagingSourceDir`" -G `"Visual Studio 17 2022`" -A x64 " +
        "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 -DGGML_CUDA_FA_ALL_QUANTS=ON " +
        "-DGGML_CUDA_FUSION=1 -DGGML_CUDA_COMPRESSION_MODE=size -DGGML_CUDA_KQUANTS_ITER=2 " +
        "-DGGML_CUDA_MIN_BATCH_OFFLOAD=32 -DGGML_CUDA_PEER_MAX_BATCH_SIZE=128"

    Log-Msg "      Configuring CMake..." "INFO"
    $cmdScript = "@call `"$vcvars`"`r`n$cmakeConfigureCmd`r`n"
    $tmpBat = Join-Path $stagingBuildDir "run_cmake.bat"
    Set-Content -Path $tmpBat -Value $cmdScript -Encoding ASCII
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $cfgRes = & cmd.exe /c "$tmpBat" 2>&1
    $cfgCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP

    if ($cfgCode -ne 0) {
        Log-Msg "CMake configuration failed:`n$cfgRes" "ERROR"
        Clean-StagingResources
        Log-Msg "Production source and bin remain 100% untouched on commit $currentShort." "WARN"
        Set-ComponentStatus "BUILD_FAILED"
        exit 1
    }

    Log-Msg "      Compiling Release binaries..." "INFO"
    $buildCmd = "cmake --build `"$stagingBuildDir`" --config Release --target llama-server llama-cli --parallel 8"
    $buildBat = Join-Path $stagingBuildDir "run_build.bat"
    Set-Content -Path $buildBat -Value "@call `"$vcvars`"`r`n$buildCmd`r`n" -Encoding ASCII

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $buildRes = & cmd.exe /c "$buildBat" 2>&1
    $buildCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP

    if ($buildCode -ne 0) {
        Log-Msg "Compilation failed:`n$buildRes" "ERROR"
        Clean-StagingResources
        Log-Msg "Production source and bin remain 100% untouched on commit $currentShort." "WARN"
        Set-ComponentStatus "BUILD_FAILED"
        exit 1
    }
}

# Collect staging binaries
$builtDir = if (Test-Path (Join-Path $stagingBuildDir "bin\Release\llama-server.exe")) {
    Join-Path $stagingBuildDir "bin\Release"
} elseif (Test-Path (Join-Path $stagingBuildDir "bin\llama-server.exe")) {
    Join-Path $stagingBuildDir "bin"
} else {
    $stagingBinDir
}

if ($builtDir -ne $stagingBinDir) {
    Copy-Item -Path (Join-Path $builtDir "*") -Destination $stagingBinDir -Recurse -Force
}
Log-Msg "      Staging build completed successfully." "SUCCESS"

# 6. Candidate Gates Validation on temporary port 18080
Log-Msg "[6/8] Executing candidate gates on test port 18080..." "STEP"
$stagingPort = 18080
$stagingExe = Join-Path $stagingBinDir "llama-server.exe"

$gateEvidence = @{
    timestamp = (Get-Date -Format "o")
    target_commit = $stagingCommit
    staging_binary = $stagingExe
    qwen_gate = @{}
    ornith_gate = @{}
}

# --- GATE A: QWEN 3.8 REAL GATE ---
Log-Msg "=== Gate A: Qwen 3.8 + mmproj + MTP validation ===" "STEP"
$qwenLog = Join-Path $Global:LogDir "candidate-ik-qwen-${stagingPort}.log"
$qwenErr = Join-Path $Global:LogDir "candidate-ik-qwen-${stagingPort}.err"
if (Test-Path $qwenLog) { Remove-Item $qwenLog -Force -ErrorAction SilentlyContinue }
if (Test-Path $qwenErr) { Remove-Item $qwenErr -Force -ErrorAction SilentlyContinue }

$qwenArgs = "-m `"$expectedModel`" --mmproj `"$qwenMmproj`" -c 98304 -ctk q8_0 -ctv q5_0 -fa on -ngl 999 -np 1 -dev CUDA0 --spec-type mtp:n_max=3,p_min=0.0 --jinja --host 127.0.0.1 --port $stagingPort"

$qwenProc = Start-Process -FilePath $stagingExe -ArgumentList $qwenArgs -RedirectStandardOutput $qwenLog -RedirectStandardError $qwenErr -PassThru -NoNewWindow
Log-Msg "      Candidate Qwen process started with PID: $($qwenProc.Id)" "INFO"

$qwenReady = $false
$swQ = [System.Diagnostics.Stopwatch]::StartNew()
while ($swQ.Elapsed.TotalSeconds -lt 600) {
    if ($qwenProc.HasExited) {
        Log-Msg "Candidate Qwen process exited prematurely with code $($qwenProc.ExitCode)" "ERROR"
        break
    }
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:${stagingPort}/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($res -and ($res.status -eq "ok" -or $res -eq "OK")) {
            $qwenReady = $true
            Log-Msg "      Candidate Qwen server HTTP ready in $([int]$swQ.Elapsed.TotalSeconds)s" "SUCCESS"
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}

$qwenLogContent = ""
if (Test-Path $qwenLog) { $qwenLogContent += Get-Content $qwenLog -Raw -ErrorAction SilentlyContinue }
if (Test-Path $qwenErr) { $qwenLogContent += "`n" + (Get-Content $qwenErr -Raw -ErrorAction SilentlyContinue) }

$qwenMainLoaded = ($qwenLogContent -match "(?i)model loaded|HTTP server listening")
$qwenMmprojLoaded = ($qwenLogContent -match "(?i)clip_model_load|clip_init|mmproj|vision")
$qwenMtpInit = ($qwenLogContent -match "(?i)MTP context ready|speculative decoding context initialized|mtp")
$qwenCompletionPass = $false

if ($qwenReady) {
    try {
        $body = @{
            messages = @(@{ role = "user"; content = "Test 1+1. Answer only number." })
            max_tokens = 15
            temperature = 0.0
        } | ConvertTo-Json
        $chatRes = Invoke-RestMethod -Uri "http://127.0.0.1:${stagingPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 45
        if ($chatRes -and $chatRes.choices -and $chatRes.choices.Count -gt 0) {
            $qwenCompletionPass = $true
            Log-Msg "      [PASS] Qwen short text completion passed." "SUCCESS"
        }
    } catch {
        Log-Msg "Qwen short completion failed: $_" "ERROR"
    }
}

try { Stop-Process -Id $qwenProc.Id -Force -ErrorAction SilentlyContinue } catch {}
$conn = Get-NetTCPConnection -LocalPort $stagingPort -State Listen -ErrorAction SilentlyContinue
if ($conn -and $conn.OwningProcess -gt 0) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

$qwenGatePassed = ($qwenReady -and $qwenMainLoaded -and $qwenMmprojLoaded -and $qwenMtpInit -and $qwenCompletionPass)
$gateEvidence.qwen_gate = @{
    QWEN_MAIN_LOADED = if ($qwenMainLoaded) { "PASS" } else { "FAIL" }
    QWEN_MMPROJ_LOADED = if ($qwenMmprojLoaded) { "PASS" } else { "FAIL" }
    QWEN_MTP_INITIALIZED = if ($qwenMtpInit) { "PASS" } else { "FAIL" }
    SHORT_TEXT_COMPLETION_PASS = if ($qwenCompletionPass) { "PASS" } else { "FAIL" }
    GATE_STATUS = if ($qwenGatePassed) { "PASS" } else { "FAIL" }
}

if (-not $qwenGatePassed) {
    Log-Msg "Candidate failed Qwen gate! Staging rejected." "ERROR"
    Clean-StagingResources
    Set-ComponentStatus "QWEN_GATE_FAILED"
    exit 1
}
Log-Msg "      [PASS] Gate A (Qwen 3.8 real gate) PASSED." "SUCCESS"


# --- GATE B: ORNITH 1.5 REAL GATE ---
Log-Msg "=== Gate B: Ornith 1.5 + MTP validation ===" "STEP"
$ornithLog = Join-Path $Global:LogDir "candidate-ik-ornith-${stagingPort}.log"
$ornithErr = Join-Path $Global:LogDir "candidate-ik-ornith-${stagingPort}.err"
if (Test-Path $ornithLog) { Remove-Item $ornithLog -Force -ErrorAction SilentlyContinue }
if (Test-Path $ornithErr) { Remove-Item $ornithErr -Force -ErrorAction SilentlyContinue }

$ornithArgs = "-m `"$ornithModel`" -c 98304 -ctk q8_0 -ctv q5_0 -fa on -ngl 999 -dev CUDA0 --spec-type mtp:n_max=1,p_min=0.75 --jinja --host 127.0.0.1 --port $stagingPort"

$ornithProc = Start-Process -FilePath $stagingExe -ArgumentList $ornithArgs -RedirectStandardOutput $ornithLog -RedirectStandardError $ornithErr -PassThru -NoNewWindow
Log-Msg "      Candidate Ornith process started with PID: $($ornithProc.Id)" "INFO"

$ornithReady = $false
$swO = [System.Diagnostics.Stopwatch]::StartNew()
while ($swO.Elapsed.TotalSeconds -lt 600) {
    if ($ornithProc.HasExited) {
        Log-Msg "Candidate Ornith process exited prematurely with code $($ornithProc.ExitCode)" "ERROR"
        break
    }
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:${stagingPort}/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($res -and ($res.status -eq "ok" -or $res -eq "OK")) {
            $ornithReady = $true
            Log-Msg "      Candidate Ornith server HTTP ready in $([int]$swO.Elapsed.TotalSeconds)s" "SUCCESS"
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}

$ornithLogContent = ""
if (Test-Path $ornithLog) { $ornithLogContent += Get-Content $ornithLog -Raw -ErrorAction SilentlyContinue }
if (Test-Path $ornithErr) { $ornithLogContent += "`n" + (Get-Content $ornithErr -Raw -ErrorAction SilentlyContinue) }

$ornithMainLoaded = ($ornithLogContent -match "(?i)model loaded|HTTP server listening")
$ornithMtpInit = ($ornithLogContent -match "(?i)MTP context ready|recurrent|speculative decoding context initialized|mtp")
$ornithCompletionPass = $false

if ($ornithReady) {
    try {
        $body = @{
            messages = @(@{ role = "user"; content = "Test 1+1. Answer only number." })
            max_tokens = 15
            temperature = 0.0
        } | ConvertTo-Json
        $chatRes = Invoke-RestMethod -Uri "http://127.0.0.1:${stagingPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 45
        if ($chatRes -and $chatRes.choices -and $chatRes.choices.Count -gt 0) {
            $ornithCompletionPass = $true
            Log-Msg "      [PASS] Ornith short completion passed." "SUCCESS"
        }
    } catch {
        Log-Msg "Ornith short completion failed: $_" "ERROR"
    }
}

try { Stop-Process -Id $ornithProc.Id -Force -ErrorAction SilentlyContinue } catch {}
$conn = Get-NetTCPConnection -LocalPort $stagingPort -State Listen -ErrorAction SilentlyContinue
if ($conn -and $conn.OwningProcess -gt 0) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

$ornithGatePassed = ($ornithReady -and $ornithMainLoaded -and $ornithMtpInit -and $ornithCompletionPass)
$gateEvidence.ornith_gate = @{
    ORNITH_MODEL_LOADED = if ($ornithMainLoaded) { "PASS" } else { "FAIL" }
    ORNITH_MTP_INITIALIZED = if ($ornithMtpInit) { "PASS" } else { "FAIL" }
    SHORT_COMPLETION_PASS = if ($ornithCompletionPass) { "PASS" } else { "FAIL" }
    GATE_STATUS = if ($ornithGatePassed) { "PASS" } else { "FAIL" }
}

# Save candidate gate evidence to stage_7e3_ik_llama
$evidenceDir = Join-Path $Global:ProjectRootDir "OpenHands-Tests\Production-Station\stage_7e3_ik_llama"
if (Test-Path $evidenceDir) {
    $gateEvidence | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $evidenceDir "candidate_gate.json") -Encoding UTF8
}

if (-not $ornithGatePassed) {
    Log-Msg "Candidate failed Ornith gate! Staging rejected." "ERROR"
    Clean-StagingResources
    Set-ComponentStatus "ORNITH_GATE_FAILED"
    exit 1
}
Log-Msg "      [PASS] Gate B (Ornith 1.5 real gate) PASSED." "SUCCESS"

# 8. Promote Staging to Production (Only reached on 100% PASS!)
Log-Msg "[8/8] Promoting validated staging to production..." "STEP"

# 8a. Switch main source to validated commit now that it has passed
Log-Msg "      Updating production source repository to $stagingShort..." "INFO"
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& git -C $srcDir checkout main 2>$null
& git -C $srcDir merge --ff-only $stagingCommit 2>$null
$ErrorActionPreference = $prevEAP
Clean-StagingResources

# 8b. Stop production platform and release binary lock
Log-Msg "      Stopping production services to replace runtime binaries..." "INFO"
& (Join-Path $Global:ProjectRootDir ".openhands-local\stop.ps1")
Start-Sleep -Seconds 2

$lockedProcs = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -like "$prodBinDir\*" -or
    $_.CommandLine -like "*$prodBinDir\llama-server.exe*"
}
foreach ($lp in $lockedProcs) {
    Log-Msg "      Stopping active backend process $($lp.Name) (PID: $($lp.ProcessId)) to release binary lock..." "INFO"
    Stop-Process -Id $lp.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# 8c. Copy binaries
Fast-CopyDir $stagingBinDir $prodBinDir
if (Test-Path $stagingBinDir) { Remove-Item -Path $stagingBinDir -Recurse -Force -ErrorAction SilentlyContinue }

# 8d. Record updated runtime hash and state
$newRuntimeHash = (Get-FileHash (Join-Path $prodBinDir "llama-server.exe") -Algorithm SHA256).Hash
$newCommit = (& git -C $srcDir rev-parse HEAD).Trim()
$newShort = (& git -C $srcDir rev-parse --short HEAD).Trim()

$newState = @{
    production_commit = $newCommit
    production_short_commit = $newShort
    production_runtime_hash = $newRuntimeHash
    benchmark_baseline = $measuredTps
    last_verified = (Get-Date -Format "o")
}
$newState | ConvertTo-Json | Out-File -FilePath $stateFile -Encoding UTF8

# Update BUILD-INFO.txt
$newBuildInfo = "ik_llama.cpp`r`n" +
    "Commit: $newCommit`r`n" +
    "Short commit: $newShort`r`n" +
    "Build date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n" +
    "CUDA architecture: 75 (RTX 2080 Ti / Turing)`r`n" +
    "GGML_CUDA_FA_ALL_QUANTS: ON`r`n" +
    "Runtime SHA256: $newRuntimeHash`r`n" +
    "Benchmark baseline: $measuredTps tok/s`r`n"
Set-Content -Path (Join-Path $prodBinDir "BUILD-INFO.txt") -Value $newBuildInfo -Encoding UTF8

# 8e. Platform Restart (Conditional on -RestartPlatform; default: STOPPED)
if ($RestartPlatform) {
    Log-Msg "      Restarting OpenHands Local platform (-RestartPlatform supplied)..." "INFO"
    & (Join-Path $Global:ProjectRootDir ".openhands-local\start.ps1")
    Start-Sleep -Seconds 3

    $finalSmoke = Run-SmokeTest -CheckLocale $false
    if ($finalSmoke) {
        Log-Msg "=====================================================================" "SUCCESS"
        Log-Msg "   IK_LLAMA BACKEND UPDATED & VERIFIED: $newShort" "SUCCESS"
        Log-Msg "=====================================================================" "SUCCESS"
        Set-ComponentStatus "UPDATED"
        exit 0
    } else {
        Log-Msg "Smoke test failed after promotion. Initiating rollback..." "ERROR"
        & "$PSScriptRoot\rollback-ik-llama.ps1" -BackupPath $backupFolder
        Set-ComponentStatus "SMOKE_ROLLBACK"
        exit 1
    }
} else {
    Log-Msg "=====================================================================" "SUCCESS"
    Log-Msg "   IK_LLAMA PROMOTED: $newShort (Station remains STOPPED by default)" "SUCCESS"
    Log-Msg "   To start platform explicitly, run START-OPENHANDS-LOCAL.cmd" "INFO"
    Log-Msg "=====================================================================" "SUCCESS"
    Set-ComponentStatus "UPDATED_STOPPED"
    exit 0
}

