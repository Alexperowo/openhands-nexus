# OpenHands Local - Idempotent Working Profile UI Patcher for Agent Canvas
$ErrorActionPreference = 'Stop'

$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$CanvasDir = Join-Path $appData 'npm\node_modules\@openhands\agent-canvas\build'
$IndexHtml = Join-Path $CanvasDir 'index.html'

if (-not (Test-Path $IndexHtml)) {
    Write-Warning "index.html not found at: $IndexHtml"
    exit 0
}

$Content = [System.IO.File]::ReadAllText($IndexHtml, [System.Text.Encoding]::UTF8)

$LoaderId = 'id="oh-wp-loader"'
$LoaderSnippet = '<script id="oh-wp-loader">(function(){var isSec=(window.location.protocol==="https:"||window.location.port==="8443");var base=isSec?(window.location.origin+"/voice-api"):"http://127.0.0.1:18002";var ts=Date.now();var l=document.createElement("link");l.rel="stylesheet";l.href=base+"/working-profile-ui.css?t="+ts;document.head.appendChild(l);var s=document.createElement("script");s.src=base+"/working-profile-ui.js?t="+ts;s.defer=true;document.head.appendChild(s);})();</script>'

if ($Content.Contains($LoaderId)) {
    # Remove existing to allow clean update
    $Content = $Content -replace '<script id="oh-wp-loader">[\s\S]*?</script>', ''
}

if (-not $Content.Contains('</body>')) {
    Write-Error "index.html structure changed: '</body>' tag not found. Manual review required."
    exit 1
}

# Inject before </body>
$NewContent = $Content.Replace('</body>', "$LoaderSnippet</body>")
[System.IO.File]::WriteAllText($IndexHtml, $NewContent, [System.Text.Encoding]::UTF8)
Write-Host '[Working Profile UI] Successfully injected Working Profile UI loader into index.html' -ForegroundColor Green
