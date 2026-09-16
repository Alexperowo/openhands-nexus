# OpenHands Nexus - Automated Binary Deployment & Extraction
# Ensures all necessary inference binaries, routers, and voice libraries are present.
[CmdletBinding()]
param(
    [string]$ReleaseVersion = "v1.0.0",
    [string]$CustomZipPath = "",
    [switch]$ForceExtract
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "       OPENHANDS NEXUS - INFERENCE & ROUTER BINARIES SETUP" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$binChecks = @(
    @{ Name = "ik_llama (Dual-GPU MTP Engine)"; Path = Join-Path $ProjectRoot "ik_llama\bin\llama-server.exe" },
    @{ Name = "llama-swap (LLM Router)";        Path = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe" },
    @{ Name = "transcribe.dll (GigaAM Voice)";  Path = Join-Path $ProjectRoot "transcribe-build-shared\bin\Release\transcribe.dll" },
    @{ Name = "MoE Expert Cache (Qwen 122B)";  Path = Join-Path $ProjectRoot "LLM-tests\Qwen122B-Expert-Cache\bin\llama-server.exe" }
)

$missing = @()
foreach ($bc in $binChecks) {
    if (-not (Test-Path $bc.Path)) {
        $missing += $bc
    }
}

if ($missing.Count -eq 0 -and -not $ForceExtract) {
    Write-Host "[OK] All required station binaries are already installed and verified:" -ForegroundColor Green
    foreach ($bc in $binChecks) {
        Write-Host "     + $($bc.Name): $($bc.Path)" -ForegroundColor Gray
    }
    Write-Host ""
    exit 0
}

Write-Host "[!] Missing or re-extraction requested for $($missing.Count) components:" -ForegroundColor Yellow
foreach ($m in $missing) {
    Write-Host "    - $($m.Name) ($($m.Path))" -ForegroundColor Yellow
}
Write-Host ""

# Step 1: Locate archive (local first, then download)
$targetZip = ""
if ($CustomZipPath -and (Test-Path $CustomZipPath)) {
    $targetZip = $CustomZipPath
    Write-Host "[1/2] Using user-specified binaries archive: $targetZip" -ForegroundColor Green
} else {
    $localReleasesDir = Join-Path $ProjectRoot "Archive\releases"
    $localCandidate = Join-Path $localReleasesDir "openhands-nexus-binaries-${ReleaseVersion}.zip"
    if (Test-Path $localCandidate) {
        $targetZip = $localCandidate
        Write-Host "[1/2] Found local release archive: $targetZip" -ForegroundColor Green
    } else {
        # Check any zip in Archive\releases
        $anyZip = Get-ChildItem -Path $localReleasesDir -Filter "openhands-nexus-binaries-*.zip" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($anyZip) {
            $targetZip = $anyZip.FullName
            Write-Host "[1/2] Found local release archive: $targetZip" -ForegroundColor Green
        }
    }
}

if (-not $targetZip) {
    # Download from GitHub Releases
    $releaseUrl = "https://github.com/Alexperowo/openhands-nexus/releases/download/${ReleaseVersion}/openhands-nexus-binaries-${ReleaseVersion}.zip"
    $downloadDir = Join-Path $ProjectRoot "Temp"
    if (-not (Test-Path $downloadDir)) { New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null }
    $downloadTarget = Join-Path $downloadDir "openhands-nexus-binaries-${ReleaseVersion}.zip"

    Write-Host "[1/2] Downloading release binaries archive from GitHub..." -ForegroundColor Yellow
    Write-Host "      URL: $releaseUrl" -ForegroundColor Gray
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Invoke-WebRequest -Uri $releaseUrl -OutFile $downloadTarget -TimeoutSec 120
        $sw.Stop()
        if (Test-Path $downloadTarget) {
            $szMb = [math]::Round((Get-Item $downloadTarget).Length / 1MB, 2)
            Write-Host "      [OK] Downloaded $szMb MB in $([math]::Round($sw.Elapsed.TotalSeconds, 1))s" -ForegroundColor Green
            $targetZip = $downloadTarget
        }
    } catch {
        Write-Host "      [WARN] Could not download from GitHub release: $_" -ForegroundColor Yellow
        Write-Host "             If air-gapped, place 'openhands-nexus-binaries-${ReleaseVersion}.zip' into Archive\releases\." -ForegroundColor Gray
    }
}

# Step 2: Extract archive
if ($targetZip -and (Test-Path $targetZip)) {
    Write-Host "[2/2] Extracting binaries into project root: $ProjectRoot..." -ForegroundColor Yellow
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($targetZip, $ProjectRoot)
        Write-Host "      [OK] Binaries extracted successfully." -ForegroundColor Green
    } catch {
        # Fallback to Expand-Archive
        try {
            Expand-Archive -Path $targetZip -DestinationPath $ProjectRoot -Force
            Write-Host "      [OK] Binaries extracted via Expand-Archive." -ForegroundColor Green
        } catch {
            Write-Host "      [ERROR] Extraction failed: $_" -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "[2/2] Attempting upstream tool fetch fallback..." -ForegroundColor Yellow
    
    # Fallback for llama-swap
    $swapBin = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
    if (-not (Test-Path $swapBin)) {
        Write-Host "      Running update-llama-swap.ps1 -Update..." -ForegroundColor Cyan
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "OpenHands-Update\scripts\update-llama-swap.ps1") -Update
    }

    # Fallback for llama-mainline
    $mainlineBin = Join-Path $ProjectRoot "llama-mainline\b10991\llama-server.exe"
    if (-not (Test-Path $mainlineBin)) {
        Write-Host "      Running update-llama-mainline.ps1 -Update..." -ForegroundColor Cyan
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "OpenHands-Update\scripts\update-llama-mainline.ps1") -Update
    }
}

# Verify deployment
Write-Host ""
$stillMissing = 0
foreach ($bc in $binChecks) {
    if (Test-Path $bc.Path) {
        Write-Host "  [OK  ] $($bc.Name)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $($bc.Name) (Still missing: $($bc.Path))" -ForegroundColor Red
        $stillMissing++
    }
}

Write-Host ""
if ($stillMissing -eq 0) {
    Write-Host "All inference binaries and router tools are successfully deployed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Warning: Some custom binaries are still missing. Build or extract archive." -ForegroundColor Yellow
    exit 1
}
