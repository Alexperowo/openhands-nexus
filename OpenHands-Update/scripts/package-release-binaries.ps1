# OpenHands Nexus - Release Binaries Packager Script
# Packages all validated inference engines, LLM routers, and speech libraries into a distributable zip archive.
[CmdletBinding()]
param(
    [string]$Version = "v1.0.0",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "Archive\releases"
}
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$zipName = "openhands-nexus-binaries-${Version}.zip"
$zipPath = Join-Path $OutputDir $zipName
$shaPath = Join-Path $OutputDir "${zipName}.sha256.txt"
$stagingDir = Join-Path $ProjectRoot "Temp\package-staging"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "     OPENHANDS NEXUS - PACKAGING RELEASE BINARIES ($Version)" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $stagingDir) {
    Remove-Item -Path $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

# 1. ik_llama (Dual-GPU MTP Inference Engine)
Write-Host "[1/5] Packaging ik_llama (Dual-GPU MTP)..." -ForegroundColor Yellow
$ikStage = Join-Path $stagingDir "ik_llama\bin"
New-Item -ItemType Directory -Path $ikStage -Force | Out-Null
$ikFiles = @("llama-server.exe", "llama-cli.exe", "llama.dll", "mtmd.dll", "BUILD-INFO.txt")
foreach ($f in $ikFiles) {
    $src = Join-Path $ProjectRoot "ik_llama\bin\$f"
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $ikStage -Force
        Write-Host "      + ik_llama/bin/$f" -ForegroundColor Gray
    } else {
        Write-Host "      [WARN] File not found: $src" -ForegroundColor Yellow
    }
}

# 2. llama-swap (Dynamic LLM Router)
Write-Host "[2/5] Packaging llama-swap (LLM Router)..." -ForegroundColor Yellow
$swapStage = Join-Path $stagingDir "llama-swap\bin"
New-Item -ItemType Directory -Path $swapStage -Force | Out-Null
$swapSrc = Join-Path $ProjectRoot "llama-swap\bin\llama-swap.exe"
if (Test-Path $swapSrc) {
    Copy-Item -Path $swapSrc -Destination $swapStage -Force
    Write-Host "      + llama-swap/bin/llama-swap.exe" -ForegroundColor Gray
} else {
    Write-Host "      [WARN] llama-swap.exe not found!" -ForegroundColor Yellow
}

# 3. transcribe.dll (FUTO GigaAM v3 Local Voice STT)
Write-Host "[3/5] Packaging local-voice STT libraries..." -ForegroundColor Yellow
$transStage = Join-Path $stagingDir "transcribe-build-shared\bin\Release"
New-Item -ItemType Directory -Path $transStage -Force | Out-Null
$voiceStage = Join-Path $stagingDir "local-voice\bin"
New-Item -ItemType Directory -Path $voiceStage -Force | Out-Null

$transFiles = @("transcribe.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll")
foreach ($tf in $transFiles) {
    $src = Join-Path $ProjectRoot "transcribe-build-shared\bin\Release\$tf"
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $transStage -Force
        Copy-Item -Path $src -Destination $voiceStage -Force
        Write-Host "      + transcribe-build-shared/bin/Release/$tf" -ForegroundColor Gray
    }
}
$cliSrc = Join-Path $ProjectRoot "local-voice\bin\transcribe-cli.exe"
if (Test-Path $cliSrc) {
    Copy-Item -Path $cliSrc -Destination $voiceStage -Force
    Write-Host "      + local-voice/bin/transcribe-cli.exe" -ForegroundColor Gray
}

# 4. MoE Expert Cache Backend (Qwen 122B)
Write-Host "[4/5] Packaging MoE Hot-Expert Cache Backend..." -ForegroundColor Yellow
$moeStage = Join-Path $stagingDir "LLM-tests\Qwen122B-Expert-Cache\bin"
New-Item -ItemType Directory -Path $moeStage -Force | Out-Null
$moeSrcDir = Join-Path $ProjectRoot "LLM-tests\Qwen122B-Expert-Cache\bin"
if (Test-Path $moeSrcDir) {
    Copy-Item -Path (Join-Path $moeSrcDir "*") -Destination $moeStage -Recurse -Force
    Write-Host "      + LLM-tests/Qwen122B-Expert-Cache/bin/*" -ForegroundColor Gray
}

# 5. Compress Archive
Write-Host "[5/5] Creating ZIP archive: $zipPath..." -ForegroundColor Yellow
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($stagingDir, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
$zipItem = Get-Item $zipPath
$zipSizeMb = [math]::Round($zipItem.Length / 1MB, 2)
Write-Host "      [OK] Archive created ($zipSizeMb MB)" -ForegroundColor Green

# Generate SHA256 Checksum
$hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash
"$hash  $zipName" | Out-File -FilePath $shaPath -Encoding ASCII
Write-Host "      [OK] SHA256: $hash" -ForegroundColor Green

# Manifest
$manifest = @{
    version = $Version
    archive_name = $zipName
    sha256 = $hash
    size_mb = $zipSizeMb
    created_at = (Get-Date -Format "o")
    components = @{
        ik_llama = "06e20d7 (Dual-GPU MTP, sm_75;120)"
        llama_swap = "v255"
        local_voice_stt = "FUTO GigaAM v3 (transcribe.dll)"
        moe_expert_cache = "bccbacd (Hot-Expert Cache for Qwen 122B)"
    }
}
$manifestPath = Join-Path $OutputDir "release-manifest-${Version}.json"
$manifest | ConvertTo-Json -Depth 4 | Out-File -FilePath $manifestPath -Encoding ASCII
Write-Host "      [OK] Manifest: $manifestPath" -ForegroundColor Green

Remove-Item -Path $stagingDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   RELEASE BINARIES ARCHIVE BUILT SUCCESSFULLY!" -ForegroundColor Green
Write-Host "   Archive: $zipPath (${zipSizeMb} MB)" -ForegroundColor White
Write-Host "=====================================================================" -ForegroundColor Cyan
