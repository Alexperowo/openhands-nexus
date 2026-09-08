# Patch / Re-apply Voice Bridge UI Integration for OpenHands Agent Canvas
$ErrorActionPreference = "Stop"

$CanvasDir = "C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas\build"
$IndexHtml = "$CanvasDir\index.html"
$IndexOrig = "$CanvasDir\index.html.original"

if (-not (Test-Path $CanvasDir)) {
    Write-Warning "Agent Canvas build directory not found: $CanvasDir"
    exit 0
}

# 1. Backup original index.html if not already backed up
if (-not (Test-Path $IndexOrig)) {
    Copy-Item $IndexHtml $IndexOrig -Force
    Write-Host "[Voice UI] Created backup: $IndexOrig"
}

# 2. Check if injection exists, if not or if old snippet exists, clean and re-inject
$Content = [System.IO.File]::ReadAllText($IndexHtml, [System.Text.Encoding]::UTF8)
$InjectSnippet = '<link rel="stylesheet" href="http://127.0.0.1:18002/voice-bridge.css"><script src="http://127.0.0.1:18002/voice-bridge.js" defer></script>'

# Remove any previous relative or outdated script tags
$Cleaned = $Content -replace '<link rel="stylesheet" href="/voice-bridge\.css">', ''
$Cleaned = $Cleaned -replace '<script src="/voice-bridge\.js" defer></script>', ''
$Cleaned = $Cleaned -replace [regex]::Escape($InjectSnippet), ''

# Inject before </body>
$NewContent = $Cleaned -replace '</body>', "$InjectSnippet</body>"
[System.IO.File]::WriteAllText($IndexHtml, $NewContent, [System.Text.Encoding]::UTF8)
Write-Host "[Voice UI] Successfully verified and applied Voice Bridge injection to index.html"