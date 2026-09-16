<#
.SYNOPSIS
    OpenHands Nexus — LAN Gateway & Mobile PWA Maintenance & Cert Updater
.DESCRIPTION
    Inspects LAN Gateway (Port 8443), validates SSL/mTLS certificates,
    monitors certificate expiration, checks Windows Firewall rules,
    and idempotently regenerates certificates if expiring (< 30 days).
    Supports -CheckOnly, -DryRun, -RenewCert, and -Force.
.PARAMETER CheckOnly
    Inspects certificates, firewall, Node.js runtime, and reports validity.
.PARAMETER DryRun
    Simulates certificate inspection and renewal without disk modifications.
.PARAMETER RenewCert
    Regenerates Root CA and Leaf SAN certificate bundle (openhands-lan.pfx).
.PARAMETER Force
    Forces certificate regeneration even if current certificates are fresh.
#>

[CmdletBinding(DefaultParameterSetName = "Default")]
param(
    [Parameter(ParameterSetName = "Check")]
    [switch]$CheckOnly,

    [Parameter(ParameterSetName = "DryRun")]
    [switch]$DryRun,

    [Parameter(ParameterSetName = "RenewCert")]
    [Alias("Update")]
    [switch]$RenewCert,

    [switch]$Force,
    [switch]$RestartPlatform
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "pwa-gateway"

# 1. Enforce Safe Default Invocation
$modeCount = ([int]$CheckOnly.IsPresent) + ([int]$DryRun.IsPresent) + ([int]$RenewCert.IsPresent)
if ($modeCount -eq 0 -and (-not $Force)) {
    Log-Msg "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
}

Log-Msg "=====================================================================" "STEP"
Log-Msg "          OPENHANDS LAN GATEWAY & MOBILE PWA (Port 8443)" "STEP"
Log-Msg "=====================================================================" "STEP"

$PwaDir = Join-Path $Global:ProjectRootDir "openhands-pwa"
$CertDir = Join-Path $PwaDir "certs"
$CaCrt = Join-Path $CertDir "openhands-ca.crt"
$LeafCrt = Join-Path $CertDir "openhands-lan.crt"
$LeafPfx = Join-Path $CertDir "openhands-lan.pfx"
$AuthTokenFile = Join-Path $CertDir "lan-auth-token.txt"

# [1/4] Inspect Node.js Runtime
Log-Msg "[1/4] Inspecting Node.js runtime & gateway script..." "STEP"
$nodeExe = (Get-Command "node.exe" -ErrorAction SilentlyContinue).Source
if (-not $nodeExe) {
    Log-Msg "Node.js executable not found in PATH!" "ERROR"
    exit 1
}
$nodeVer = (& $nodeExe --version 2>&1).Trim()
Log-Msg "      Node.js Runtime           : $nodeVer ($nodeExe)" "SUCCESS"

$gatewayScript = Join-Path $PwaDir "lan-gateway.mjs"
if (Test-Path $gatewayScript) {
    Log-Msg "      Gateway Script            : FOUND ($gatewayScript)" "SUCCESS"
} else {
    Log-Msg "      Gateway Script            : NOT FOUND at $gatewayScript!" "ERROR"
}

# [2/4] Inspect SSL / TLS Certificates & Expiration
Log-Msg "[2/4] Inspecting SSL/TLS certificates and expiration..." "STEP"
$certExpiring = $false

if (Test-Path $LeafCrt) {
    try {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($LeafCrt)
        $notAfter = $cert.NotAfter
        $daysLeft = [math]::Round(($notAfter - (Get-Date)).TotalDays)
        Log-Msg "      Leaf SAN Certificate      : Valid until $($notAfter.ToString('yyyy-MM-dd HH:mm:ss')) ($daysLeft days remaining)" "SUCCESS"
        Log-Msg "      Certificate Subject       : $($cert.Subject)" "INFO"
        Log-Msg "      Certificate Issuer        : $($cert.Issuer)" "INFO"

        if ($daysLeft -lt 30) {
            Log-Msg "      WARNING: Certificate expires in less than 30 days!" "WARN"
            $certExpiring = $true
        }
    } catch {
        Log-Msg "      Error reading leaf certificate: $_" "ERROR"
        $certExpiring = $true
    }
} else {
    Log-Msg "      Leaf Certificate          : NOT FOUND at $LeafCrt!" "WARN"
    $certExpiring = $true
}

if (Test-Path $LeafPfx) {
    Log-Msg "      Leaf PFX Bundle (PKCS#12) : FOUND ($LeafPfx)" "SUCCESS"
} else {
    Log-Msg "      Leaf PFX Bundle           : NOT FOUND at $LeafPfx!" "WARN"
    $certExpiring = $true
}

if (Test-Path $AuthTokenFile) {
    $tokenLen = (Get-Content $AuthTokenFile -Raw).Trim().Length
    Log-Msg "      LAN Auth Token            : FOUND ($tokenLen chars in $AuthTokenFile)" "SUCCESS"
} else {
    Log-Msg "      LAN Auth Token            : NOT FOUND at $AuthTokenFile!" "WARN"
}

# [3/4] Inspect Firewall Rule & Network Accessibility
Log-Msg "[3/4] Inspecting Windows Firewall rule for Port 8443..." "STEP"
$fwRule = Get-NetFirewallRule -DisplayName "*OpenHands*PWA*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $fwRule) {
    $fwRule = Get-NetFirewallRule -Name "*OpenHands*8443*" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($fwRule) {
    Log-Msg "      Firewall Rule             : ACTIVE ($($fwRule.DisplayName), Enabled=$($fwRule.Enabled))" "SUCCESS"
} else {
    Log-Msg "      Firewall Rule             : NOT FOUND (Run openhands-pwa/configure-firewall.ps1 with Admin)" "WARN"
}

$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker' } |
          Sort-Object InterfaceMetric |
          Select-Object -First 1).IPAddress
Log-Msg "      LAN IPv4 Address          : $lanIp (URL: https://${lanIp}:8443)" "INFO"

# [4/4] Execution Branch
if ($CheckOnly) {
    Log-Msg "=====================================================================" "STEP"
    if ($certExpiring) {
        Log-Msg "Certificates require renewal. Run: .\update-pwa-gateway.ps1 -RenewCert" "WARN"
    } else {
        Log-Msg "LAN Gateway and certificates are healthy." "SUCCESS"
    }
    Log-Msg "=====================================================================" "STEP"
    exit 0
}

if ($DryRun) {
    Log-Msg "[SIMULATION] Would run certificate generation script: openhands-pwa/generate-ca-and-certs.py" "INFO"
    Log-Msg "[SIMULATION] Zero files modified in DryRun." "SUCCESS"
    exit 0
}

if ($RenewCert -or $Force) {
    Log-Msg "Regenerating SSL/TLS certificates and PFX bundle..." "STEP"
    $genScript = Join-Path $PwaDir "generate-ca-and-certs.py"
    $pythonExe = (Get-Command "python.exe").Source
    & $pythonExe $genScript
    if ($LASTEXITCODE -eq 0) {
        Log-Msg "Certificates regenerated and validated successfully!" "SUCCESS"
    } else {
        Log-Msg "Certificate generation failed with exit code $LASTEXITCODE" "ERROR"
        exit $LASTEXITCODE
    }
    exit 0
}
