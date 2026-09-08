# OpenHands Local - Idempotent Working Profile UI Patcher for Agent Canvas
$ErrorActionPreference = 'Stop'

$CanvasDir = 'C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas\build'
$IndexHtml = Join-Path $CanvasDir 'index.html'

if (-not (Test-Path $IndexHtml)) {
    Write-Warning "index.html not found at: $IndexHtml"
    exit 0
}

$Content = [System.IO.File]::ReadAllText($IndexHtml, [System.Text.Encoding]::UTF8)

$LoaderSnippet = '<script id="oh-wp-loader">(function(){var base=window.location.origin+"/voice-api";var ts=Date.now();var l=document.createElement("link");l.rel="stylesheet";l.href=base+"/working-profile-ui.css?t="+ts;document.head.appendChild(l);var s=document.createElement("script");s.src=base+"/working-profile-ui.js?t="+ts;s.defer=true;document.head.appendChild(s);})();</script>'

if ($Content.Contains($LoaderId)) {
    # Remove existing to allow clean update
    $Content = $Content -replace '<script id="oh-wp-loader">.*?</script>', ''
}

# Inject before </body>
$NewContent = $Content.Replace('</body>', "$LoaderSnippet</body>")
[System.IO.File]::WriteAllText($IndexHtml, $NewContent, [System.Text.Encoding]::UTF8)
Write-Host '[Working Profile UI] Successfully injected Working Profile UI loader into index.html' -ForegroundColor Green
