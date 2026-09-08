# OpenHands Local - Agent Canvas PWA & Mobile Adaptation Patcher
$ErrorActionPreference = "Stop"

$CanvasBase = "C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas"
$BuildDir = Join-Path $CanvasBase "build"
$SourceDir = "K:\Project\openhands-pwa"
$IndexHtml = Join-Path $BuildDir "index.html"
$IndexOrig = Join-Path $BuildDir "index.html.orig-pwa"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "            OPENHANDS LOCAL - MOBILE PWA PATCHER" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan

# 1. Verify build directory
if (-not (Test-Path $BuildDir)) {
    Write-Warning "Agent Canvas build directory not found at: $BuildDir"
    exit 0
}

# 2. Deploy static PWA assets
Write-Host "[1/4] Deploying manifest.webmanifest, sw.js, and mobile-pwa.css..." -ForegroundColor Yellow
Copy-Item (Join-Path $SourceDir "manifest.webmanifest") (Join-Path $BuildDir "manifest.webmanifest") -Force
Copy-Item (Join-Path $SourceDir "manifest.webmanifest") (Join-Path $BuildDir "site.webmanifest") -Force
Copy-Item (Join-Path $SourceDir "sw.js") (Join-Path $BuildDir "sw.js") -Force
Copy-Item (Join-Path $SourceDir "mobile-pwa.css") (Join-Path $BuildDir "mobile-pwa.css") -Force
Write-Host "      PWA assets copied to $BuildDir" -ForegroundColor Green

# 3. Backup index.html if first run
if (-not (Test-Path $IndexOrig)) {
    Copy-Item $IndexHtml $IndexOrig -Force
    Write-Host "[2/4] Created pristine PWA backup: $IndexOrig" -ForegroundColor Gray
} else {
    Write-Host "[2/4] PWA backup already exists." -ForegroundColor Gray
}

# 4. Patch index.html
Write-Host "[3/4] Patching index.html for PWA manifest, service worker & mobile styles..." -ForegroundColor Yellow
$content = [System.IO.File]::ReadAllText($IndexHtml, [System.Text.Encoding]::UTF8)

# Head tags to inject
$pwaHeadSnippet = '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#18181b"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="stylesheet" href="/mobile-pwa.css">'

# Service worker snippet to inject before </body>
$swSnippet = '<script>if("serviceWorker" in navigator){window.addEventListener("load",function(){navigator.serviceWorker.register("/sw.js").catch(function(e){console.warn("SW register failed:",e);});});}</script>'

# Dynamic Voice loader (ensures voice works over both localhost and LAN HTTPS without mixed content)
$dynamicVoiceSnippet = '<script id="oh-voice-loader">(function(){var isSec=(window.location.protocol==="https:"||window.location.port==="8443");var base=isSec?(window.location.origin+"/voice-api"):"http://127.0.0.1:18002";var l=document.createElement("link");l.rel="stylesheet";l.href=base+"/voice-bridge.css";document.head.appendChild(l);var s=document.createElement("script");s.src=base+"/voice-bridge.js";s.defer=true;document.head.appendChild(s);})();</script>'

# Remove any previous PWA injections for clean idempotency
$cleaned = $content -replace [regex]::Escape($pwaHeadSnippet), ''
$cleaned = $cleaned -replace [regex]::Escape($swSnippet), ''
$cleaned = $cleaned -replace '<script id="oh-voice-loader">[\s\S]*?</script>', ''

# If static voice tags exist from patch-agent-canvas-voice.ps1, upgrade them to the dynamic loader
$staticVoiceSnippet = '<link rel="stylesheet" href="http://127.0.0.1:18002/voice-bridge.css"><script src="http://127.0.0.1:18002/voice-bridge.js" defer></script>'
if ($cleaned.Contains($staticVoiceSnippet)) {
    $cleaned = $cleaned.Replace($staticVoiceSnippet, $dynamicVoiceSnippet)
} elseif (-not $cleaned.Contains("oh-voice-loader")) {
    $cleaned = $cleaned -replace '</body>', "$dynamicVoiceSnippet</body>"
}

# Inject head snippet before </head>
$patched = $cleaned -replace '</head>', "$pwaHeadSnippet</head>"

# Inject service worker before </body>
$patched = $patched -replace '</body>', "$swSnippet</body>"

[System.IO.File]::WriteAllText($IndexHtml, $patched, [System.Text.Encoding]::UTF8)
Write-Host "      index.html patched with manifest, service worker, and mobile CSS." -ForegroundColor Green

# 4b. Patch ingress.mjs and static-server.mjs to enforce loopback binding (127.0.0.1:8000)
$ingressFile = Join-Path $CanvasBase "scripts\ingress.mjs"
if (Test-Path $ingressFile) {
    $ingressContent = [System.IO.File]::ReadAllText($ingressFile, [System.Text.Encoding]::UTF8)
    if (-not $ingressContent.Contains('host: (process.env.INGRESS_HOST || "127.0.0.1").trim()')) {
        $ingressContent = $ingressContent -replace 'port: 8000,(\r?\n)', "port: 8000,`$1    host: (process.env.INGRESS_HOST || `"127.0.0.1`").trim(),`$1"
    }
    if (-not $ingressContent.Contains('host: (args.host || env.INGRESS_HOST || "127.0.0.1").trim()')) {
        $ingressContent = $ingressContent -replace 'port: args\.port \|\| parseInt\(env\.INGRESS_PORT, 10\) \|\| 8000,(\r?\n)', "port: args.port || parseInt(env.INGRESS_PORT, 10) || 8000,`$1    host: (args.host || env.INGRESS_HOST || `"127.0.0.1`").trim(),`$1"
    }
    if ($ingressContent.Contains('server.listen(config.port, () => {')) {
        $ingressContent = $ingressContent.Replace('server.listen(config.port, () => {', 'server.listen(config.port, config.host, () => {')
    }
    [System.IO.File]::WriteAllText($ingressFile, $ingressContent, [System.Text.Encoding]::UTF8)
    Write-Host "      ingress.mjs patched to bind to loopback 127.0.0.1." -ForegroundColor Green
}

$staticFile = Join-Path $CanvasBase "scripts\static-server.mjs"
if (Test-Path $staticFile) {
    $staticContent = [System.IO.File]::ReadAllText($staticFile, [System.Text.Encoding]::UTF8)

    # (a) Loopback binding
    if ($staticContent.Contains('host: "::"') -or $staticContent.Contains('host: process.env.INGRESS_HOST || "127.0.0.1"')) {
        $staticContent = $staticContent -replace 'host:.*', 'host: (process.env.STATIC_HOST || process.env.INGRESS_HOST || "127.0.0.1").trim(),'
    }

    # (b) Replace immutable 1-year /assets/ cache with no-cache+ETag revalidation.
    #     This ensures in-place file patches (e.g. localization injections) are
    #     visible immediately without requiring users to clear browser data.
    $immutableHeader = 'res.setHeader("Cache-Control", "public, max-age=31536000, immutable");'
    $noCache = 'res.setHeader("Cache-Control", "no-cache, must-revalidate"); // local patch: no immutable'
    if ($staticContent.Contains($immutableHeader)) {
        $staticContent = $staticContent.Replace($immutableHeader, $noCache)
        Write-Host "      static-server.mjs: /assets/ changed from immutable to no-cache." -ForegroundColor Green
    }

    # (c) Inject Clear-Site-Data: "cache" into HTML responses so Chrome purges
    #     stale cached assets on every page load.  Safe for localhost-only use.
    $htmlHeader = '"Cache-Control": "no-cache",'
    $htmlHeaderWithClear = '"Cache-Control": "no-cache",' + "`n    " + '"Clear-Site-Data": "\"cache\"",'
    if ($staticContent.Contains($htmlHeader) -and -not $staticContent.Contains('Clear-Site-Data')) {
        $staticContent = $staticContent.Replace($htmlHeader, $htmlHeaderWithClear)
        Write-Host "      static-server.mjs: Clear-Site-Data injected into HTML responses." -ForegroundColor Green
    }

    [System.IO.File]::WriteAllText($staticFile, $staticContent, [System.Text.Encoding]::UTF8)
    Write-Host "      static-server.mjs patched." -ForegroundColor Green
}

# 5. Verification
Write-Host "[4/4] Verifying PWA patch..." -ForegroundColor Yellow
$verifyContent = [System.IO.File]::ReadAllText($IndexHtml, [System.Text.Encoding]::UTF8)
$hasManifest = $verifyContent.Contains("manifest.webmanifest")
$hasSW = $verifyContent.Contains("/sw.js")
$hasMobileCss = $verifyContent.Contains("mobile-pwa.css")
$hasVoiceAnchors = $verifyContent.Contains("voice-bridge.css") -and $verifyContent.Contains("voice-bridge.js")

if ($hasManifest -and $hasSW -and $hasMobileCss -and $hasVoiceAnchors) {
    Write-Host "[OK] PWA Patch applied and verified successfully!" -ForegroundColor Green
    exit 0
} else {
    Write-Error "Verification failed! Manifest: $hasManifest, SW: $hasSW, CSS: $hasMobileCss, Voice: $hasVoiceAnchors"
    exit 1
}
