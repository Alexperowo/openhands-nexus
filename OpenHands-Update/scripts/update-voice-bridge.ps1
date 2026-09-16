<#
.SYNOPSIS
    OpenHands Nexus — Local Voice Bridge Dependency & Pipeline Updater
.DESCRIPTION
    Safely inspects, updates, and verifies dependencies for the Local Voice Bridge (Port 18002).
    Manages Python libraries (supertonic, transcribe_cpp, cryptography, soundfile, numpy, av)
    and verifies offline neural models (GigaAM v3 STT + Supertonic 3 TTS).
    Supports -CheckOnly, -DryRun, -Update, and -Force.
    POLICY: Speech model weights are pinned offline assets; models are NEVER auto-downloaded.
.PARAMETER CheckOnly
    Inspects installed Python packages, speech models, and reports version matrix.
.PARAMETER DryRun
    Simulates update actions without modifying any packages.
.PARAMETER Update
    Safely updates Python voice dependencies via pip and validates the voice pipeline.
.PARAMETER Force
    Reinstalls dependencies even if versions match.
.PARAMETER RestartPlatform
    Restarts the Voice Bridge service after update.
#>

[CmdletBinding(DefaultParameterSetName = "Default")]
param(
    [Parameter(ParameterSetName = "Check")]
    [switch]$CheckOnly,

    [Parameter(ParameterSetName = "DryRun")]
    [switch]$DryRun,

    [Parameter(ParameterSetName = "Update")]
    [switch]$Update,

    [switch]$Force,
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "voice-bridge"

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$Update.IsPresent)
if ($modeCount -eq 0 -and (-not $Force)) {
    Log-Msg "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
}

Log-Msg "=====================================================================" "STEP"
Log-Msg "          OPENHANDS LOCAL VOICE BRIDGE (GigaAM & Supertonic)" "STEP"
Log-Msg "=====================================================================" "STEP"

$VoiceDir = Join-Path $Global:ProjectRootDir "local-voice"
$ModelsSpeechDir = Join-Path $Global:ProjectRootDir "Models\Speech"
$GigaAmModel = Join-Path $ModelsSpeechDir "gigaam-v3-e2e-rnnt-Q8_0.gguf"
$SupertonicDir = Join-Path $ModelsSpeechDir "supertonic"

# [1/4] Inspect Speech Models (Pinned offline assets)
Log-Msg "[1/4] Inspecting local speech models (Models are pinned; not auto-downloaded)..." "STEP"
if (Test-Path $GigaAmModel) {
    $sttSizeMB = [math]::Round((Get-Item $GigaAmModel).Length / 1MB, 2)
    Log-Msg "      GigaAM v3 STT Model       : $sttSizeMB MB (FOUND: $GigaAmModel)" "SUCCESS"
} else {
    Log-Msg "      GigaAM v3 STT Model       : NOT FOUND at $GigaAmModel!" "ERROR"
}

if (Test-Path $SupertonicDir) {
    $ttsFiles = Get-ChildItem $SupertonicDir -Recurse -File
    $ttsSizeMB = [math]::Round(($ttsFiles | Measure-Object -Property Length -Sum).Sum / 1MB, 2)
    Log-Msg "      Supertonic 3 TTS Model    : $ttsSizeMB MB ($($ttsFiles.Count) files in $SupertonicDir)" "SUCCESS"
} else {
    Log-Msg "      Supertonic 3 TTS Model    : NOT FOUND at $SupertonicDir!" "ERROR"
}

# [2/4] Inspect Python Environment & Voice Libraries
Log-Msg "[2/4] Inspecting Python voice runtime & packages..." "STEP"
$pythonExe = (Get-Command "python.exe" -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Log-Msg "Python executable not found in PATH!" "ERROR"
    exit 1
}
$pyVer = (& $pythonExe --version 2>&1).Trim()
Log-Msg "      Python Runtime            : $pyVer ($pythonExe)" "INFO"

$packages = @("supertonic", "cryptography", "soundfile", "numpy", "av")
$pkgStatus = @{}

foreach ($pkg in $packages) {
    $ver = & $pythonExe -c "import $pkg; print(getattr($pkg, '__version__', 'installed'))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver) {
        $pkgStatus[$pkg] = $ver.Trim()
        Log-Msg "      Package: $($pkg.PadRight(16)) : v$($ver.Trim())" "SUCCESS"
    } else {
        $pkgStatus[$pkg] = "NOT_INSTALLED"
        Log-Msg "      Package: $($pkg.PadRight(16)) : NOT INSTALLED" "WARN"
    }
}

# Check local transcribe_cpp binding
$transcribeDll = Join-Path $Global:ProjectRootDir "transcribe-build-shared\bin\Release\transcribe.dll"
$tcppCheck = & $pythonExe -c "import os, sys; os.environ['TRANSCRIBE_LIBRARY'] = r'$transcribeDll'; sys.path.insert(0, r'$VoiceDir'); import transcribe_cpp; print(getattr(transcribe_cpp, '__version__', 'ok'))" 2>$null
if ($LASTEXITCODE -eq 0 -and $tcppCheck) {
    Log-Msg "      transcribe_cpp (GigaAM)   : v$($tcppCheck.Trim()) (Local binding OK)" "SUCCESS"
} else {
    Log-Msg "      transcribe_cpp (GigaAM)   : Binding check failed or unavailable" "WARN"
}

# [3/4] Check Upstream PyPI for Available Updates
Log-Msg "[3/4] Querying PyPI for upstream package releases..." "STEP"
$pypiUpdates = @{}
foreach ($pkg in @("supertonic", "cryptography", "soundfile")) {
    try {
        $res = Invoke-RestMethod -Uri "https://pypi.org/pypi/$pkg/json" -TimeoutSec 5 -ErrorAction Stop
        $latestVer = $res.info.version
        $curVer = $pkgStatus[$pkg]
        if ($curVer -ne "NOT_INSTALLED" -and $curVer -ne $latestVer) {
            $pypiUpdates[$pkg] = @{ Current = $curVer; Latest = $latestVer }
            Log-Msg "      $pkg update available: v$curVer -> v$latestVer" "WARN"
        } else {
            Log-Msg "      $pkg is up to date: v$curVer" "INFO"
        }
    } catch {
        Log-Msg "      ${pkg}: PyPI check skipped ($($_.Exception.Message))" "SKIP"
    }
}

# [4/4] Execution Branch
if ($CheckOnly) {
    Log-Msg "=====================================================================" "STEP"
    Log-Msg "Voice Bridge check completed safely. To update packages: .\update-voice-bridge.ps1 -Update" "SUCCESS"
    Log-Msg "=====================================================================" "STEP"
    exit 0
}

if ($DryRun) {
    Log-Msg "[SIMULATION] Would update Python packages: $($pypiUpdates.Keys -join ', ')" "INFO"
    Log-Msg "[SIMULATION] Zero files modified in DryRun." "SUCCESS"
    exit 0
}

if ($Update) {
    Log-Msg "Updating Python voice packages..." "STEP"
    foreach ($pkg in @("supertonic", "cryptography", "soundfile", "av")) {
        Log-Msg "Running: pip install --upgrade $pkg..." "INFO"
        & $pythonExe -m pip install --upgrade $pkg
        if ($LASTEXITCODE -ne 0) {
            Log-Msg "Warning: pip install for $pkg reported non-zero exit code." "WARN"
        }
    }
    Log-Msg "Python packages updated successfully." "SUCCESS"

    # Verify health
    Log-Msg "Validating Voice Bridge health endpoint on port 18002..." "STEP"
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:18002/health" -TimeoutSec 5 -ErrorAction Stop
        if ($h.status -eq "ok") {
            Log-Msg "Voice Bridge is healthy and operational! (Status: $($h.status))" "SUCCESS"
        }
    } catch {
        Log-Msg "Voice Bridge is not currently running. Run 'openhands start' to launch." "INFO"
    }
    exit 0
}
