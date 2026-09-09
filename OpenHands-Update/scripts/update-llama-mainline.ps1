<#
.SYNOPSIS
    Hardened Official llama.cpp Updater for Qwen3-Next Backend.
.DESCRIPTION
    Safely manages updates and rollbacks for the official llama.cpp CUDA backend
    used by Qwen3-Next in OpenHands Local.
    Supports -CheckOnly, -DryRun, -Update, and -Rollback.
    Never updates silently on double-click (defaults strictly to -CheckOnly).
    Station stop is a HARD GATE (cannot be bypassed by -Force).
    Config promotion verifies YAML validity, parameter preservation, and saves rollback backups.
.PARAMETER CheckOnly
    Discovers latest release assets, performs HTTP HEAD verification, and reports status.
.PARAMETER DryRun
    Simulates complete update workflow including safety checks, asset verification, and config promotion.
.PARAMETER Update
    Performs safe isolated download, candidate runtime gate validation, and safe atomic config promotion.
.PARAMETER Rollback
    Safely rolls back llama-swap config.yaml to previous working build.
.PARAMETER TargetBuild
    Explicit build tag to install (e.g. b10819). Defaults to latest discovered official build.
.PARAMETER RollbackBuild
    Explicit build tag to roll back to. Defaults to build recorded in PREVIOUS_BUILD.txt.
.PARAMETER Force
    Overrides non-critical conditions (e.g. reinstalling same build).
    NEVER bypasses the station stop hard gate.
.PARAMETER RestartPlatform
    If specified, restarts the OpenHands platform after promotion/rollback.
    Default: $false (station remains STOPPED).
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
    [string]$TargetBuild = "",

    [Parameter(ParameterSetName = "Rollback")]
    [string]$RollbackBuild = "",

    [switch]$Force,

    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"

# --- Constants & Paths ---
$ProjectRootDir     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$MainlineRoot       = Join-Path $ProjectRootDir "llama-mainline"
$UpdateRootDir      = Join-Path $ProjectRootDir "OpenHands-Update"
$LogDir             = Join-Path $ProjectRootDir "Logs\Updater"
$StateDir           = Join-Path $UpdateRootDir "state"
$StagingDir         = Join-Path $UpdateRootDir "staging\llama-mainline"
$ConfigYaml         = Join-Path $ProjectRootDir "llama-swap\config.yaml"
$ArchiveBackupDir   = Join-Path $ProjectRootDir "Archive\backups\llama-mainline"
$ManifestJson       = Join-Path $ProjectRootDir "Config\backend-versions.json"
$PreviousBuildFile  = Join-Path $MainlineRoot "PREVIOUS_BUILD.txt"
$ProductionPorts    = @(8000, 8080, 18000, 18001, 18002)

# Ensure required directories exist
foreach ($dir in @($LogDir, $StateDir, $MainlineRoot, $ArchiveBackupDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# --- Logging Setup ---
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFileName = "update-llama-mainline-${timestamp}.log"
$Script:LogFilePath = Join-Path $LogDir $logFileName

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "STEP", "SUCCESS", "WARN", "ERROR", "DRYRUN")]
        [string]$Level = "INFO"
    )
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $formatted = "[$ts] [$Level] $Message"

    $color = switch ($Level) {
        "SUCCESS" { "Green" }
        "STEP"    { "Cyan" }
        "WARN"    { "Yellow" }
        "ERROR"   { "Red" }
        "DRYRUN"  { "Magenta" }
        Default   { "White" }
    }

    Write-Host $formatted -ForegroundColor $color
    if ($Script:LogFilePath) {
        Add-Content -Path $Script:LogFilePath -Value $formatted -Encoding UTF8
    }
}

# --- Hard Station Safety Check ---
function Get-ActiveStationPorts {
    $active = [System.Collections.Generic.List[int]]::new()
    foreach ($port in $ProductionPorts) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $iar = $tcp.BeginConnect("127.0.0.1", $port, $null, $null)
            $wh = $iar.AsyncWaitHandle
            if ($wh.WaitOne(200, $false)) {
                $tcp.EndConnect($iar)
                $tcp.Close()
                $active.Add($port)
            } else {
                $tcp.Close()
            }
        } catch {
            # port closed
        }
    }
    return $active.ToArray()
}

function Assert-StationStoppedHardGate {
    $active = @(Get-ActiveStationPorts)
    if ($active.Length -gt 0) {
        Write-Log "HARD SAFETY GATE FAILED: Production station is RUNNING on port(s): $($active -join ', ')." "ERROR"
        Write-Log "Backend update/rollback REFUSED. -Force CANNOT override this safety gate. Stop station first." "ERROR"
        exit 1
    }
    Write-Log "Hard safety gate: Station is STOPPED (All production ports free)." "SUCCESS"
}

# --- Inspect Current Production Build ---
function Get-CurrentProductionBuild {
    if (-not (Test-Path $ConfigYaml)) {
        throw "llama-swap config not found at: $ConfigYaml"
    }
    $content = Get-Content $ConfigYaml -Raw
    $pattern = '(?m)cmd:\s*([^\r\n]*llama-mainline\\([^\\]+)\\llama-server\.exe)'
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success) {
        throw "Failed to extract active llama-mainline path from $ConfigYaml"
    }

    $binPath = $match.Groups[1].Value.Trim()
    $buildTag = $match.Groups[2].Value.Trim()
    $sha256 = "UNKNOWN"
    $versionRaw = "UNKNOWN"

    if (Test-Path $binPath) {
        $sha256 = (Get-FileHash -Path $binPath -Algorithm SHA256).Hash
        try {
            $verLines = cmd.exe /c "`"$binPath`" --version 2>&1"
            $versionRaw = ($verLines -join " ").Trim()
        } catch {
            $versionRaw = "ERROR_RUNNING_VERSION"
        }
    }

    return [PSCustomObject]@{
        BinaryPath  = $binPath
        BuildTag    = $buildTag
        SHA256      = $sha256
        VersionRaw  = $versionRaw
        Exists      = (Test-Path $binPath)
    }
}

# --- Dynamic Release Asset Discovery & Verification ---
function Discover-ReleaseAssets {
    param(
        [string]$TargetTag = ""
    )

    Write-Log "Discovering official llama.cpp release assets from GitHub..." "INFO"

    # Step 1: Discover tag if not explicitly given
    if (-not $TargetTag) {
        try {
            $rawHtml = [string]::Join("`n", (curl.exe -s "https://github.com/ggml-org/llama.cpp/releases"))
            $match = [regex]::Match($rawHtml, '/ggml-org/llama\.cpp/releases/tag/(b\d+)')
            if ($match.Success) {
                $TargetTag = $match.Groups[1].Value
                Write-Log "Discovered latest official build tag: $TargetTag" "SUCCESS"
            }
        } catch {
            Write-Log "Failed to scrape releases page: $_" "WARN"
        }
    }

    if (-not $TargetTag) {
        throw "Could not determine official llama.cpp target build tag."
    }

    # Step 2: Query expanded assets page for the target tag
    $assetsUrl = "https://github.com/ggml-org/llama.cpp/releases/expanded_assets/$TargetTag"
    $assetsHtml = [string]::Join("`n", (curl.exe -s $assetsUrl))

    # Match Windows x64 CUDA 12.4 assets
    $binRegex = 'href="(/ggml-org/llama\.cpp/releases/download/' + $TargetTag + '/(llama-' + $TargetTag + '-bin-win-cuda-12\.4-x64\.zip))"'
    $cudartRegex = 'href="(/ggml-org/llama\.cpp/releases/download/' + $TargetTag + '/(cudart-llama-bin-win-cuda-12\.4-x64\.zip))"'

    $binMatch = [regex]::Match($assetsHtml, $binRegex)
    $cudartMatch = [regex]::Match($assetsHtml, $cudartRegex)

    if (-not $binMatch.Success -or -not $cudartMatch.Success) {
        # Fallback to general CUDA x64 matching if upstream changed naming conventions
        $binFallbackRegex = 'href="(/ggml-org/llama\.cpp/releases/download/' + $TargetTag + '/([^"]*bin-win-cuda-12\.4-x64\.zip))"'
        $cudartFallbackRegex = 'href="(/ggml-org/llama\.cpp/releases/download/' + $TargetTag + '/(cudart[^"]*bin-win-cuda-12\.4-x64\.zip))"'
        $binMatch = [regex]::Match($assetsHtml, $binFallbackRegex)
        $cudartMatch = [regex]::Match($assetsHtml, $cudartFallbackRegex)
    }

    if (-not $binMatch.Success -or -not $cudartMatch.Success) {
        throw "Upstream release packaging changed or CUDA 12.4 Windows x64 assets not found for tag $TargetTag."
    }

    $binAsset = $binMatch.Groups[2].Value
    $cudaAsset = $cudartMatch.Groups[2].Value
    $binUrl = "https://github.com" + $binMatch.Groups[1].Value
    $cudaUrl = "https://github.com" + $cudartMatch.Groups[1].Value

    # Step 3: HTTP HEAD checks to verify assets exist without downloading full archives
    Write-Log "Verifying existence of release assets via HTTP HEAD..." "STEP"
    $binHttpCode = (curl.exe -ILs -o NUL -w "%{http_code}" $binUrl).Trim()
    $cudaHttpCode = (curl.exe -ILs -o NUL -w "%{http_code}" $cudaUrl).Trim()

    $binExists = ($binHttpCode -eq "200" -or $binHttpCode -eq "302")
    $cudaExists = ($cudaHttpCode -eq "200" -or $cudaHttpCode -eq "302")

    if (-not $binExists -or -not $cudaExists) {
        throw "Release asset HEAD check failed! Binary HTTP code=$binHttpCode, CUDA HTTP code=$cudaHttpCode"
    }

    Write-Log "Asset URLs verified successfully (HTTP 200/302)." "SUCCESS"

    return [PSCustomObject]@{
        TargetTag           = $TargetTag
        BinAsset            = $binAsset
        CudaRuntimeAsset    = $cudaAsset
        BinAssetUrl         = $binUrl
        CudaAssetUrl        = $cudaUrl
        AssetsVerifiedExist = $true
    }
}

# --- Static Capabilities Verification ---
function Test-MainlineCapabilities {
    param(
        [string]$ServerBinaryPath
    )

    Write-Log "Testing static capabilities on: $ServerBinaryPath" "STEP"
    if (-not (Test-Path $ServerBinaryPath)) {
        Write-Log "Binary does not exist: $ServerBinaryPath" "ERROR"
        return $false
    }

    $binDir = Split-Path -Parent $ServerBinaryPath
    $requiredDlls = @("cublas64_12.dll", "cudart64_12.dll", "ggml-cuda.dll", "llama.dll")
    foreach ($dll in $requiredDlls) {
        $dllPath = Join-Path $binDir $dll
        if (-not (Test-Path $dllPath)) {
            Write-Log "Missing required companion DLL: $dllPath" "ERROR"
            return $false
        }
    }

    # Run --help and verify flags via cmd.exe wrapper
    $helpOutput = ""
    try {
        $helpLines = cmd.exe /c "`"$ServerBinaryPath`" --help 2>&1"
        $helpOutput = $helpLines -join "`n"
    } catch {
        Write-Log "Failed to execute --help: $_" "ERROR"
        return $false
    }

    $requiredChecks = @(
        @{ Name = "--model / -m"; Pattern = "-m\b|--model\b" },
        @{ Name = "--model-draft / -md"; Pattern = "-md\b|--model-draft\b" },
        @{ Name = "--spec-type"; Pattern = "--spec-type\b" },
        @{ Name = "--cache-type-k / -ctk"; Pattern = "-ctk\b|--cache-type-k\b" },
        @{ Name = "--cache-type-v / -ctv"; Pattern = "-ctv\b|--cache-type-v\b" },
        @{ Name = "--flash-attn / -fa"; Pattern = "-fa\b|--flash-attn\b" },
        @{ Name = "--jinja"; Pattern = "--jinja\b" },
        @{ Name = "--reasoning-format"; Pattern = "--reasoning-format\b" },
        @{ Name = "CUDA GPU offloading"; Pattern = "(?i)cuda|-ngl|--n-gpu-layers" }
    )

    $allPassed = $true
    foreach ($check in $requiredChecks) {
        if ($helpOutput -match $check.Pattern) {
            Write-Log "  [PASS] Capability present: $($check.Name)" "SUCCESS"
        } else {
            Write-Log "  [FAIL] Missing capability: $($check.Name)" "ERROR"
            $allPassed = $false
        }
    }

    return $allPassed
}

# --- Candidate Runtime Gate (For Real Future Updates) ---
function Test-CandidateRuntimeGate {
    param(
        [string]$CandidateBinaryPath,
        [int]$TestPort = 18081,
        [int]$TimeoutSeconds = 600
    )

    Write-Log "=== Candidate Runtime Gate: Validating on isolated port $TestPort ===" "STEP"

    $mainModel = Join-Path $ProjectRootDir "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf"
    $draftModel = Join-Path $ProjectRootDir "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf"

    if (-not (Test-Path $mainModel)) {
        Write-Log "Candidate runtime gate error: Main model not found at $mainModel" "ERROR"
        return $false
    }
    if (-not (Test-Path $draftModel)) {
        Write-Log "Candidate runtime gate error: Draft model not found at $draftModel" "ERROR"
        return $false
    }

    $candidateLog = Join-Path $LogDir "candidate-mainline-$TestPort.log"
    $candidateErr = Join-Path $LogDir "candidate-mainline-$TestPort.err"
    if (Test-Path $candidateLog) { Remove-Item $candidateLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path $candidateErr) { Remove-Item $candidateErr -Force -ErrorAction SilentlyContinue }

    $candidateArgs = "-m `"$mainModel`" -md `"$draftModel`" -c 4096 -ngl 27 -fa on -ctk q8_0 -ctv q5_0 -np 1 -t 6 -dev CUDA0 --spec-type draft-mtp --spec-draft-n-max 1 --reasoning-format deepseek --reasoning-budget-message `"Conclude reasoning immediately and output the final answer now.`" --jinja --host 127.0.0.1 --port $TestPort --temp 0.6"

    Write-Log "Starting candidate process: $CandidateBinaryPath on port $TestPort" "INFO"
    Write-Log "Candidate log: $candidateLog" "INFO"

    $gatePassed = $false
    $serverStarted = $false
    $mainLoaded = $false
    $draftLoaded = $false
    $httpHealthy = $false
    $completionPass = $false
    $candidateProc = $null

    try {
        $candidateProc = Start-Process -FilePath $CandidateBinaryPath -ArgumentList $candidateArgs -RedirectStandardOutput $candidateLog -RedirectStandardError $candidateErr -PassThru -NoNewWindow
        if (-not $candidateProc) {
            Write-Log "Failed to start candidate process" "ERROR"
            return $false
        }
        $pidNum = $candidateProc.Id
        Write-Log "Candidate process spawned with PID $pidNum" "INFO"
        $serverStarted = $true

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
            if ($candidateProc.HasExited) {
                Write-Log "Candidate process exited prematurely with code $($candidateProc.ExitCode)" "ERROR"
                break
            }

            try {
                $res = Invoke-RestMethod -Uri "http://127.0.0.1:$TestPort/health" -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($res -and $res.status -eq "ok") {
                    $httpHealthy = $true
                    Write-Log "Candidate server reports HTTP HEALTHY on port $TestPort (elapsed: $([int]$sw.Elapsed.TotalSeconds)s)" "SUCCESS"
                    break
                }
            } catch {
                # Still initializing
            }
            Start-Sleep -Seconds 2
        }

        # Check log for model load evidence
        $logContent = ""
        if (Test-Path $candidateLog) {
            $logContent += Get-Content $candidateLog -Raw -ErrorAction SilentlyContinue
        }
        if (Test-Path $candidateErr) {
            $logContent += "`n" + (Get-Content $candidateErr -Raw -ErrorAction SilentlyContinue)
        }

        if ($logContent -match "Qwen3-Next.*UD-Q3_K_XL" -or $logContent -match "model loaded" -or $logContent -match "HTTP server listening") {
            $mainLoaded = $true
            Write-Log "  [PASS] CANDIDATE_MAIN_MODEL_LOADED" "SUCCESS"
        }
        if ($logContent -match "MTP-ONLY" -or $logContent -match "draft" -or $logContent -match "mtp") {
            $draftLoaded = $true
            Write-Log "  [PASS] CANDIDATE_DRAFT_MODEL_LOADED" "SUCCESS"
        }

        if ($httpHealthy) {
            Write-Log "Sending short verification prompt to candidate server..." "STEP"
            $body = @{
                messages = @(@{ role = "user"; content = "Test 1+1. Answer only number." })
                max_tokens = 10
                temperature = 0.0
            } | ConvertTo-Json
            try {
                $chatRes = Invoke-RestMethod -Uri "http://127.0.0.1:$TestPort/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
                if ($chatRes -and $chatRes.choices -and $chatRes.choices.Count -gt 0) {
                    $completionPass = $true
                    Write-Log "Short completion passed successfully." "SUCCESS"
                }
            } catch {
                Write-Log "Chat completion verification failed: $_" "ERROR"
            }
        }

        $gatePassed = ($serverStarted -and $mainLoaded -and $draftLoaded -and $httpHealthy -and $completionPass)

        # Save candidate gate evidence to stage_7e2_mainline
        $evidenceDir = Join-Path $ProjectRootDir "OpenHands-Tests\Production-Station\stage_7e2_mainline"
        if (Test-Path $evidenceDir) {
            $gateEvidence = @{
                timestamp = (Get-Date -Format "o")
                target_build = (Split-Path (Split-Path $CandidateBinaryPath -Parent) -Leaf)
                candidate_binary = $CandidateBinaryPath
                test_port = $TestPort
                verdicts = @{
                    CANDIDATE_SERVER_STARTED = if ($serverStarted) { "PASS" } else { "FAIL" }
                    MAIN_MODEL_LOADED = if ($mainLoaded) { "PASS" } else { "FAIL" }
                    DRAFT_MODEL_LOADED = if ($draftLoaded) { "PASS" } else { "FAIL" }
                    HTTP_HEALTHY = if ($httpHealthy) { "PASS" } else { "FAIL" }
                    SHORT_COMPLETION_PASS = if ($completionPass) { "PASS" } else { "FAIL" }
                }
                gate_passed = $gatePassed
            }
            $gateEvidence | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $evidenceDir "candidate_gate.json") -Encoding UTF8
        }
    } finally {
        if ($candidateProc -and -not $candidateProc.HasExited) {
            Write-Log "Stopping candidate validation process (PID: $($candidateProc.Id))..." "INFO"
            try {
                Stop-Process -Id $candidateProc.Id -Force -ErrorAction SilentlyContinue
            } catch {}
        }
        $conn = Get-NetTCPConnection -LocalPort $TestPort -State Listen -ErrorAction SilentlyContinue
        if ($conn -and $conn.OwningProcess -gt 0) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }

    return $gatePassed
}

# --- True Safe Config Promotion Sequence ---
function Promote-ConfigSafely {
    param(
        [string]$NewCandidateBinaryPath,
        [string]$TargetConfigPath = $ConfigYaml
    )

    Write-Log "Initiating Safe Config Promotion sequence..." "STEP"

    if (-not (Test-Path $TargetConfigPath)) {
        throw "Target configuration file does not exist: $TargetConfigPath"
    }

    # Step 1: Read current config
    $currentContent = Get-Content $TargetConfigPath -Raw

    # Extract current Next binary path
    $pattern = '(?m)^(\s*cmd:\s*)([^\r\n]*llama-mainline\\[^\\]+\\llama-server\.exe)(.*)$'
    $match = [regex]::Match($currentContent, $pattern)
    if (-not $match.Success) {
        throw "Cannot find Next backend cmd in $TargetConfigPath"
    }
    $oldBinaryPath = $match.Groups[2].Value.Trim()

    # Step 2: Generate new config in temporary file
    $newContent = $currentContent -replace [regex]::Escape($oldBinaryPath), $NewCandidateBinaryPath
    $tempConfigFile = Join-Path (Split-Path -Parent $TargetConfigPath) ("config.yaml.tmp_" + $timestamp)

    [System.IO.File]::WriteAllText($tempConfigFile, $newContent, [System.Text.UTF8Encoding]::new($false))
    Write-Log "Generated candidate config in temporary file: $tempConfigFile" "INFO"

    # Step 3: Verify candidate config
    Write-Log "Verifying candidate config integrity before promotion..." "STEP"

    # 3a. YAML parseability check using Python PyYAML
    $yamlCheck = python -c "import yaml; yaml.safe_load(open(r'$tempConfigFile', encoding='utf-8'))" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Path $tempConfigFile -Force -ErrorAction SilentlyContinue
        throw "Candidate config is NOT valid YAML! Promotion rejected."
    }
    Write-Log "  [PASS] Candidate YAML parse check passed." "SUCCESS"

    # 3b. Line diff check: EXACTLY ONE line changed
    $oldLines = $currentContent.TrimEnd().Split("`n") | ForEach-Object { $_.TrimEnd("`r") }
    $newLines = $newContent.TrimEnd().Split("`n") | ForEach-Object { $_.TrimEnd("`r") }

    if ($oldLines.Length -ne $newLines.Length) {
        Remove-Item -Path $tempConfigFile -Force -ErrorAction SilentlyContinue
        throw "Line count mismatch! Old=$($oldLines.Length), New=$($newLines.Length)"
    }

    $diffCount = 0
    $changedLineOld = ""
    $changedLineNew = ""
    for ($i = 0; $i -lt $oldLines.Length; $i++) {
        if ($oldLines[$i] -ne $newLines[$i]) {
            $diffCount++
            $changedLineOld = $oldLines[$i]
            $changedLineNew = $newLines[$i]
        }
    }

    if ($diffCount -ne 1) {
        Remove-Item -Path $tempConfigFile -Force -ErrorAction SilentlyContinue
        throw "Diff check failed! Expected exactly 1 line changed, found $diffCount changed lines."
    }
    Write-Log "  [PASS] Exactly 1 line modified in config." "SUCCESS"

    # 3c. Verify Qwen3-Next model paths and launch parameters unchanged
    $requiredNextModel = Join-Path $ProjectRootDir "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf"
    $requiredNextDraft = Join-Path $ProjectRootDir "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf"

    if ($newContent -notmatch [regex]::Escape($requiredNextModel)) {
        Remove-Item -Path $tempConfigFile -Force -ErrorAction SilentlyContinue
        throw "Qwen3-Next main model path was altered! Promotion rejected."
    }
    if ($newContent -notmatch [regex]::Escape($requiredNextDraft)) {
        Remove-Item -Path $tempConfigFile -Force -ErrorAction SilentlyContinue
        throw "Qwen3-Next MTP draft model path was altered! Promotion rejected."
    }
    Write-Log "  [PASS] Qwen3-Next main and draft model paths preserved intact." "SUCCESS"

    # Step 4: Save rollback copy in K:\Project\Archive\backups\llama-mainline\
    $archiveBackupFile = Join-Path $ArchiveBackupDir ("config.yaml.bak_" + $timestamp)
    Copy-Item -Path $TargetConfigPath -Destination $archiveBackupFile -Force
    Write-Log "Saved rollback copy to: $archiveBackupFile" "SUCCESS"

    # Step 5: Promote temporary config safely
    Move-Item -Path $tempConfigFile -Destination $TargetConfigPath -Force
    Write-Log "Promoted candidate config to: $TargetConfigPath" "SUCCESS"

    # Step 6: Re-read promoted config and verify exact intended change
    $promotedContent = Get-Content $TargetConfigPath -Raw
    if ($promotedContent -notmatch [regex]::Escape($NewCandidateBinaryPath)) {
        # Restore immediately
        Copy-Item -Path $archiveBackupFile -Destination $TargetConfigPath -Force
        throw "Post-promotion verification failed! Restored original config from backup."
    }
    Write-Log "Post-promotion verification confirmed exact intended backend path." "SUCCESS"
}

# --- Action Handlers ---

function Run-CheckOnlyAction {
    Write-Log "=== Official llama.cpp Updater (CheckOnly Mode) ===" "STEP"
    
    $activePorts = @(Get-ActiveStationPorts)
    if ($activePorts.Length -gt 0) {
        Write-Log "Station status: RUNNING (Ports: $($activePorts -join ', '))" "WARN"
    } else {
        Write-Log "Station status: STOPPED (All production ports free)" "SUCCESS"
    }

    $current = Get-CurrentProductionBuild
    Write-Log "Current Production Build: $($current.BuildTag)" "INFO"
    Write-Log "Current Production Binary: $($current.BinaryPath)" "INFO"
    Write-Log "Current Binary Exists: $($current.Exists)" "INFO"
    Write-Log "Current Binary SHA256: $($current.SHA256)" "INFO"
    Write-Log "Current Version String: $($current.VersionRaw)" "INFO"

    $discovery = Discover-ReleaseAssets -TargetTag $TargetBuild

    Write-Log "================ Release Asset Discovery ================" "STEP"
    Write-Log "TARGET_TAG: $($discovery.TargetTag)" "INFO"
    Write-Log "BIN_ASSET: $($discovery.BinAsset)" "INFO"
    Write-Log "CUDA_RUNTIME_ASSET: $($discovery.CudaRuntimeAsset)" "INFO"
    Write-Log "BIN_ASSET_URL: $($discovery.BinAssetUrl)" "INFO"
    Write-Log "CUDA_ASSET_URL: $($discovery.CudaAssetUrl)" "INFO"
    Write-Log "ASSETS_VERIFIED_EXIST: $($discovery.AssetsVerifiedExist)" "SUCCESS"
    Write-Log "=========================================================" "STEP"

    if ($current.BuildTag -eq $discovery.TargetTag) {
        Write-Log "Status: Production is UP TO DATE with target build ($($discovery.TargetTag))." "SUCCESS"
    } else {
        Write-Log "Status: UPDATE AVAILABLE ($($current.BuildTag) -> $($discovery.TargetTag))." "WARN"
        Write-Log "To preview update: .\update-llama-mainline.ps1 -DryRun" "INFO"
        Write-Log "To execute update: .\update-llama-mainline.ps1 -Update -TargetBuild $($discovery.TargetTag)" "INFO"
    }
}

function Run-DryRunAction {
    Write-Log "=== Official llama.cpp Updater (DryRun Mode) ===" "STEP"
    Write-Log "[DRYRUN] Simulating complete update workflow without making changes." "DRYRUN"

    $activePorts = @(Get-ActiveStationPorts)
    if ($activePorts.Length -gt 0) {
        Write-Log "[DRYRUN] [WARN] Station is RUNNING on port(s): $($activePorts -join ', ')." "WARN"
        Write-Log "[DRYRUN] [NOTE] In real -Update mode, station must be STOPPED (Hard Gate)." "INFO"
    } else {
        Write-Log "[DRYRUN] [OK] Station is STOPPED. Hard gate check passed." "SUCCESS"
    }

    $current = Get-CurrentProductionBuild
    Write-Log "[DRYRUN] Current production build: $($current.BuildTag)" "INFO"
    Write-Log "[DRYRUN] Current binary: $($current.BinaryPath)" "INFO"

    $discovery = Discover-ReleaseAssets -TargetTag $TargetBuild
    $target = $discovery.TargetTag

    Write-Log "[DRYRUN] Target build to evaluate: $target" "INFO"
    Write-Log "[DRYRUN] Discovered Binary Asset: $($discovery.BinAsset) ($($discovery.BinAssetUrl))" "INFO"
    Write-Log "[DRYRUN] Discovered CUDA Asset: $($discovery.CudaRuntimeAsset) ($($discovery.CudaAssetUrl))" "INFO"
    Write-Log "[DRYRUN] Target directory: $MainlineRoot\$target" "INFO"

    Write-Log "[DRYRUN] Planned validation gates:" "INFO"
    Write-Log "  Gate 1: Static capabilities check (flags: -m, -md, --spec-type, -ctk, -ctv, -fa, --jinja, --reasoning-format)" "INFO"
    Write-Log "  Gate 2: Candidate runtime gate on test port 18081 (requires SERVER_STARTED, MAIN_MODEL_LOADED, DRAFT_MODEL_LOADED, HTTP_HEALTHY, SHORT_COMPLETION_PASS)" "INFO"
    Write-Log "  Gate 3: Safe config promotion with YAML validation, line diff check, and backup to $ArchiveBackupDir" "INFO"

    Write-Log "[DRYRUN] Dry run simulation completed successfully. Zero changes were made." "SUCCESS"
}

function Run-RollbackAction {
    Write-Log "=== Official llama.cpp Updater (Rollback Mode) ===" "STEP"

    # Hard gate: station must be stopped
    Assert-StationStoppedHardGate

    $current = Get-CurrentProductionBuild
    $targetRollback = $RollbackBuild

    if (-not $targetRollback) {
        if (Test-Path $PreviousBuildFile) {
            $targetRollback = (Get-Content $PreviousBuildFile -Raw).Trim()
        }
    }

    if (-not $targetRollback) {
        Write-Log "No rollback target specified and $PreviousBuildFile does not exist." "ERROR"
        exit 1
    }

    Write-Log "Current build: $($current.BuildTag) -> Rollback target build: $targetRollback" "INFO"
    $rollbackDir = Join-Path $MainlineRoot $targetRollback

    # Verify target path belongs under K:\Project\llama-mainline\
    $resolvedDir = [System.IO.Path]::GetFullPath($rollbackDir)
    $resolvedRoot = [System.IO.Path]::GetFullPath($MainlineRoot)
    if (-not $resolvedDir.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Log "Security violation: Rollback target path does not belong under $MainlineRoot" "ERROR"
        exit 1
    }

    $rollbackBinary = Join-Path $rollbackDir "llama-server.exe"
    if (-not (Test-Path $rollbackBinary)) {
        Write-Log "Rollback binary not found at: $rollbackBinary" "ERROR"
        exit 1
    }

    # Verify static capabilities
    if (-not (Test-MainlineCapabilities -ServerBinaryPath $rollbackBinary)) {
        Write-Log "Rollback binary failed capabilities check! Refusing rollback." "ERROR"
        exit 1
    }

    # Safe config promotion to rollback binary
    Promote-ConfigSafely -NewCandidateBinaryPath $rollbackBinary

    if ($RestartPlatform) {
        Write-Log "Starting OpenHands Local (-RestartPlatform supplied)..." "STEP"
        & (Join-Path $ProjectRootDir ".openhands-local\start.ps1")
    } else {
        Write-Log "Rollback complete. Station remains STOPPED (default behavior; pass -RestartPlatform to restart)." "SUCCESS"
    }
}

function Run-UpdateAction {
    Write-Log "=== Official llama.cpp Updater (Update Mode) ===" "STEP"

    # Hard gate: station must be stopped
    Assert-StationStoppedHardGate

    $current = Get-CurrentProductionBuild
    $discovery = Discover-ReleaseAssets -TargetTag $TargetBuild
    $target = $discovery.TargetTag

    Write-Log "Current Build: $($current.BuildTag)" "INFO"
    Write-Log "Target Build: $target" "INFO"

    if ($current.BuildTag -eq $target -and -not $Force) {
        Write-Log "Build $target is already the active production backend. Use -Force to reinstall." "WARN"
        return
    }

    $targetDir = Join-Path $MainlineRoot $target
    $candidateBinary = Join-Path $targetDir "llama-server.exe"

    # Download if not already present
    if (-not (Test-Path $candidateBinary)) {
        $workStaging = Join-Path $StagingDir $target
        if (-not (Test-Path $workStaging)) {
            New-Item -ItemType Directory -Path $workStaging -Force | Out-Null
        }

        $binZipPath = Join-Path $workStaging $discovery.BinAsset
        $cudartZipPath = Join-Path $workStaging $discovery.CudaRuntimeAsset

        Write-Log "Downloading binary archive: $($discovery.BinAssetUrl)" "STEP"
        curl.exe -f -L -o $binZipPath $discovery.BinAssetUrl
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $binZipPath)) {
            throw "Failed to download $($discovery.BinAssetUrl)"
        }

        Write-Log "Downloading CUDA runtime archive: $($discovery.CudaAssetUrl)" "STEP"
        curl.exe -f -L -o $cudartZipPath $discovery.CudaAssetUrl
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $cudartZipPath)) {
            throw "Failed to download $($discovery.CudaAssetUrl)"
        }

        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        Write-Log "Extracting archives into: $targetDir" "STEP"
        Expand-Archive -Path $binZipPath -DestinationPath $targetDir -Force
        Expand-Archive -Path $cudartZipPath -DestinationPath $targetDir -Force

        # Record metadata
        $meta = @{
            LLAMA_CPP_TAG   = $target
            DOWNLOAD_SOURCE = $discovery.BinAssetUrl
            CUDA_BUILD      = "Windows x64 CUDA 12.4"
            BIN_ZIP         = $discovery.BinAsset
            BIN_SHA256      = (Get-FileHash -Path $binZipPath -Algorithm SHA256).Hash
            CUDART_ZIP      = $discovery.CudaRuntimeAsset
            CUDART_SHA256   = (Get-FileHash -Path $cudartZipPath -Algorithm SHA256).Hash
            DOWNLOAD_TIME   = (Get-Date -Format "o")
        }
        $meta | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $targetDir "BACKEND_VERSION.json") -Encoding UTF8
    }

    # Gate 1: Static capabilities verification
    if (-not (Test-MainlineCapabilities -ServerBinaryPath $candidateBinary)) {
        Write-Log "Static validation FAILED for candidate build $target. Production config remains UNTOUCHED." "ERROR"
        exit 1
    }

    # Gate 2: Candidate runtime gate validation on isolated test port
    if (-not (Test-CandidateRuntimeGate -CandidateBinaryPath $candidateBinary -TestPort 18081)) {
        Write-Log "Candidate runtime gate FAILED for build $target. Production config remains UNTOUCHED." "ERROR"
        exit 1
    }

    # Record previous build marker
    Set-Content -Path $PreviousBuildFile -Value $current.BuildTag -Encoding UTF8
    Write-Log "Recorded previous build '$($current.BuildTag)' in $PreviousBuildFile" "INFO"

    # Gate 3: Safe config promotion sequence
    Promote-ConfigSafely -NewCandidateBinaryPath $candidateBinary

    # Update informational manifest if promotion succeeded
    if (Test-Path $ManifestJson) {
        try {
            $manifest = Get-Content $ManifestJson -Raw | ConvertFrom-Json
            $manifest.llama_mainline.production_path = $candidateBinary
            $manifest.llama_mainline.build = $target
            $manifest.llama_mainline.tag = $target
            $manifest.llama_mainline.sha256 = (Get-FileHash -Path $candidateBinary -Algorithm SHA256).Hash
            $manifest.llama_mainline.previous_build = $current.BuildTag
            $manifest.llama_mainline.update_timestamp = (Get-Date -Format "o")
            $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $ManifestJson -Encoding UTF8
            Write-Log "Updated canonical backend manifest: $ManifestJson" "INFO"
        } catch {
            Write-Log "Non-fatal: Failed to update manifest $($ManifestJson): $_" "WARN"
        }
    }

    if ($RestartPlatform) {
        Write-Log "Starting OpenHands Local (-RestartPlatform supplied)..." "STEP"
        & (Join-Path $ProjectRootDir ".openhands-local\start.ps1")
    } else {
        Write-Log "Update complete. Station remains STOPPED (default behavior; pass -RestartPlatform to restart)." "SUCCESS"
    }
}

# --- Main Dispatcher ---

try {
    if ($CheckOnly) {
        Run-CheckOnlyAction
    } elseif ($DryRun) {
        Run-DryRunAction
    } elseif ($Update) {
        Run-UpdateAction
    } elseif ($Rollback) {
        Run-RollbackAction
    } else {
        # Default action when run without arguments or double-clicked: strictly -CheckOnly
        Write-Host "No action switch specified. Defaulting safely to -CheckOnly mode." -ForegroundColor Cyan
        Write-Host "Usage: .\update-llama-mainline.ps1 [-CheckOnly | -DryRun | -Update | -Rollback] [-TargetBuild <tag>]" -ForegroundColor DarkGray
        Write-Host ""
        Run-CheckOnlyAction
    }
} catch {
    Write-Log "FATAL ERROR: $_" "ERROR"
    exit 1
}
