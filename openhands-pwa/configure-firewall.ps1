# OpenHands Local LAN PWA Firewall Configuration
$ErrorActionPreference = "Stop"

$ruleName = "OpenHands-LAN-PWA"
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Remove-NetFirewallRule -Name $ruleName
    Write-Host "[Firewall] Removed previous rule: $ruleName" -ForegroundColor Gray
}

New-NetFirewallRule -Name $ruleName `
    -DisplayName "OpenHands Local Mobile PWA Gateway" `
    -Description "Inbound HTTPS access for OpenHands Mobile PWA over local subnet" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8443 `
    -Profile Private `
    -RemoteAddress LocalSubnet `
    -Enabled True | Out-Null

Write-Host "[OK] Firewall rule created: $ruleName" -ForegroundColor Green
Write-Host "     Port: 8443 (TCP)" -ForegroundColor Gray
Write-Host "     Profile: Private" -ForegroundColor Gray
Write-Host "     Scope: LocalSubnet" -ForegroundColor Gray
