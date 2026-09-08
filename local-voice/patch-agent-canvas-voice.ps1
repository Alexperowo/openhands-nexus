# Patch / Re-apply Voice Bridge UI Integration for OpenHands Agent Canvas
$ErrorActionPreference = "Stop"

$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$CanvasDir = Join-Path $appData 'npm\node_modules\@openhands\agent-canvas\build'
$IndexHtml = Join-Path $CanvasDir "index.html"
$IndexOrig = Join-Path $CanvasDir "index.html.original"

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
$DynamicVoiceSnippet = '<script id="oh-voice-loader">(function(){var isSec=(window.location.protocol==="https:"||window.location.port==="8443");var base=isSec?(window.location.origin+"/voice-api"):"http://127.0.0.1:18002";var l=document.createElement("link");l.rel="stylesheet";l.href=base+"/voice-bridge.css";document.head.appendChild(l);var s=document.createElement("script");s.src=base+"/voice-bridge.js";s.defer=true;document.head.appendChild(s);})();</script>'

# Remove any previous relative, static, or outdated script tags
$Cleaned = $Content -replace '<link rel="stylesheet" href="/voice-bridge\.css">', ''
$Cleaned = $Cleaned -replace '<script src="/voice-bridge\.js" defer></script>', ''
$Cleaned = $Cleaned -replace '<link rel="stylesheet" href="http://127\.0\.0\.1:18002/voice-bridge\.css"><script src="http://127\.0\.0\.1:18002/voice-bridge\.js" defer></script>', ''
$Cleaned = $Cleaned -replace '<script id="oh-voice-loader">[\s\S]*?</script>', ''

# Inject before </body>
$NewContent = $Cleaned -replace '</body>', "$DynamicVoiceSnippet</body>"
[System.IO.File]::WriteAllText($IndexHtml, $NewContent, [System.Text.Encoding]::UTF8)
Write-Host "[Voice UI] Successfully verified and applied dynamic Voice Bridge injection to index.html"