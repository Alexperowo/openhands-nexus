# OpenHands Local LAN PWA Certificate Generator (Root CA + Signed Leaf)
$ErrorActionPreference = "Stop"

$pwaDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $pwaDir "generate-ca-and-certs.py"

python "$pyScript"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to generate certificates via $pyScript"
    exit 1
}

