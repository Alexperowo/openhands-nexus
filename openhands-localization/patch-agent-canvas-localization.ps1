# OpenHands Local - Idempotent Russian Localization Patcher for Agent Canvas
$ErrorActionPreference = "Stop"

$CanvasBase = "C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas"
$BuildDir = Join-Path $CanvasBase "build"
$DistDir = Join-Path $CanvasBase "dist"
$SourceDir = "K:\Project\openhands-localization"
$RuJsonSource = Join-Path $SourceDir "ru.json"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "         OPENHANDS LOCAL - RUSSIAN LOCALIZATION INSTALLER" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan

# 1. Verify environment
if (-not (Test-Path $CanvasBase)) {
    Write-Error "Agent Canvas installation not found at: $CanvasBase"
    exit 1
}

$pkgJsonPath = Join-Path $CanvasBase "package.json"
$pkgVersion = "unknown"
if (Test-Path $pkgJsonPath) {
    try {
        $pkg = Get-Content $pkgJsonPath -Raw | ConvertFrom-Json
        $pkgVersion = $pkg.version
    } catch {}
}
Write-Host "[1/5] Agent Canvas version: $pkgVersion" -ForegroundColor Gray

if (-not (Test-Path $RuJsonSource)) {
    Write-Error "Source Russian dictionary not found: $RuJsonSource"
    exit 1
}

# 2. Deploy ru.json translation bundles to build and dist locales
Write-Host "[2/5] Deploying ru/openhands.json bundles..." -ForegroundColor Yellow
$ruBuildDir = Join-Path $BuildDir "locales\ru"
$ruDistDir = Join-Path $DistDir "locales\ru"
if (-not (Test-Path $ruBuildDir)) { New-Item -ItemType Directory -Path $ruBuildDir -Force | Out-Null }
if (-not (Test-Path $ruDistDir)) { New-Item -ItemType Directory -Path $ruDistDir -Force | Out-Null }

Copy-Item $RuJsonSource (Join-Path $ruBuildDir "openhands.json") -Force
Copy-Item $RuJsonSource (Join-Path $ruDistDir "openhands.json") -Force
Write-Host "      Copied ru.json to build/locales/ru and dist/locales/ru" -ForegroundColor Green

# 3. Deploy localization.js and localization.css
Write-Host "[3/5] Deploying runtime localization scripts..." -ForegroundColor Yellow
$locTargetDir = Join-Path $BuildDir "localization"
if (-not (Test-Path $locTargetDir)) { New-Item -ItemType Directory -Path $locTargetDir -Force | Out-Null }

Copy-Item (Join-Path $SourceDir "localization.js") (Join-Path $locTargetDir "localization.js") -Force
Copy-Item (Join-Path $SourceDir "localization.css") (Join-Path $locTargetDir "localization.css") -Force
Write-Host "      Copied localization assets to build/localization/" -ForegroundColor Green

# 4. Patch active-backend-context bundle to register 'ru' in supportedLngs and Language dropdown
Write-Host "[4/5] Registering 'ru' in i18n bundle..." -ForegroundColor Yellow
$assetsDir = Join-Path $BuildDir "assets"
$bundleFiles = Get-ChildItem $assetsDir -Filter "active-backend-context-*.js"
if ($bundleFiles.Count -eq 0) {
    Write-Warning "Could not find active-backend-context bundle in $assetsDir"
} else {
    $ukTarget = 'value:`uk`}'
    $ruLabel = [System.Text.Encoding]::UTF8.GetString([byte[]]@(0xD0,0xA0,0xD1,0x83,0xD1,0x81,0xD1,0x81,0xD0,0xBA,0xD0,0xB8,0xD0,0xB9))
    $ruReplacement = "value:``uk``},{label:``$ruLabel``,value:``ru``}"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false

    foreach ($bf in $bundleFiles) {
        $bContent = [System.IO.File]::ReadAllText($bf.FullName, [System.Text.Encoding]::UTF8)
        # Strip BOM if present (ReadAllText with UTF8 may return BOM character)
        if ($bContent.Length -gt 0 -and [int][char]$bContent[0] -eq 0xFEFF) {
            $bContent = $bContent.Substring(1)
        }
        if ($bContent.Contains('value:`ru`') -or $bContent.Contains('"ru"')) {
            Write-Host "      Bundle $($bf.Name) already contains 'ru' language definition." -ForegroundColor Gray
        } else {
            $bakFile = "$($bf.FullName).bak"
            if (-not (Test-Path $bakFile)) {
                Copy-Item $bf.FullName $bakFile -Force
                Write-Host "      Created backup: $($bf.Name).bak" -ForegroundColor Gray
            }
            
            if ($bContent.Contains($ukTarget)) {
                $patchedContent = $bContent.Replace($ukTarget, $ruReplacement)
                # Write without BOM to avoid injecting BOM into minified JS assets
                [System.IO.File]::WriteAllText($bf.FullName, $patchedContent, $utf8NoBom)
                Write-Host "      Successfully registered 'ru' in bundle: $($bf.Name)" -ForegroundColor Green
            } else {
                Write-Warning "Could not locate language anchor in $($bf.Name)"
            }
        }
    }
}

# 4b. Configure settings default language to honor localStorage or default to 'ru'
Write-Host "[4b/5] Configuring settings default language..." -ForegroundColor Yellow
$settingsFiles = Get-ChildItem -Path $AssetsDir -Filter "*settings-*.js"
$patchedSettingsCount = 0
foreach ($sf in $settingsFiles) {
    $content = [System.IO.File]::ReadAllText($sf.FullName, [System.Text.Encoding]::UTF8)
    if ($content.Contains('language:`en`') -or $content.Contains('language:"en"') -or $content.Contains("language:'en'")) {
        $clean = $content.Replace('language:`en`', 'language:(typeof localStorage!==`undefined`&&localStorage.getItem(`i18nextLng`))||`ru`')
        $clean = $clean.Replace('language:"en"', 'language:(typeof localStorage!==`undefined`&&localStorage.getItem(`i18nextLng`))||`ru`')
        $clean = $clean.Replace("language:'en'", 'language:(typeof localStorage!==`undefined`&&localStorage.getItem(`i18nextLng`))||`ru`')
        [System.IO.File]::WriteAllText($sf.FullName, $clean, [System.Text.Encoding]::UTF8)
        Write-Host "      Updated settings default language in $($sf.Name)" -ForegroundColor Green
        $patchedSettingsCount++
    } elseif ($content.Contains('localStorage.getItem(`i18nextLng`)') -or $content.Contains('localStorage.getItem("i18nextLng")')) {
        Write-Host "      Settings bundle $($sf.Name) already patched (idempotent)." -ForegroundColor Gray
        $patchedSettingsCount++
    }
}
if ($patchedSettingsCount -eq 0) {
    Write-Warning "Could not find expected 'language:`en`' anchor in any settings-*.js bundle. Upstream structure may have changed."
}

# 5. Inject runtime localization script into index.html
Write-Host "[5/5] Injecting localization layer into index.html..." -ForegroundColor Yellow
$indexHtmlPath = Join-Path $BuildDir "index.html"
if (Test-Path $indexHtmlPath) {
    $idxContent = [System.IO.File]::ReadAllText($indexHtmlPath, [System.Text.Encoding]::UTF8)
    $locSnippet = '<link rel="stylesheet" href="/localization/localization.css"><script src="/localization/localization.js"></script>'
    
    # Remove any existing snippet (at end of body or in head)
    $cleanIdx = $idxContent -replace '<link rel="stylesheet" href="/localization/localization\.css"><script src="/localization/localization\.js"( defer)?></script>', ''
    
    $idxBak = "$indexHtmlPath.orig-loc"
    if (-not (Test-Path $idxBak)) {
        Copy-Item $indexHtmlPath $idxBak -Force
        Write-Host "      Created backup: index.html.orig-loc" -ForegroundColor Gray
    }
    
    # Inject right before </head> so default language is set BEFORE React and i18next bundles initialize
    $newIdx = $cleanIdx.Replace('</head>', "$locSnippet</head>")
    [System.IO.File]::WriteAllText($indexHtmlPath, $newIdx, [System.Text.Encoding]::UTF8)
    Write-Host "      Successfully injected localization layer into index.html (<head>)" -ForegroundColor Green
}

# 6. Explicit post-install verification
Write-Host "[6/6] Verifying localization installation integrity..." -ForegroundColor Yellow

$ruBuildFile = Join-Path $ruBuildDir "openhands.json"
if (-not (Test-Path $ruBuildFile)) {
    Write-Error "Verification failed: $ruBuildFile does not exist!"
    exit 1
}
Write-Host "      [OK] ru locale bundle verified ($ruBuildFile)" -ForegroundColor Green

$bundleVerified = $false
foreach ($bf in $bundleFiles) {
    $c = [System.IO.File]::ReadAllText($bf.FullName, [System.Text.Encoding]::UTF8)
    if ($c.Contains('value:`ru`') -or $c.Contains('"ru"')) {
        $bundleVerified = $true
        Write-Host "      [OK] Bundle $($bf.Name) contains 'ru' language entry." -ForegroundColor Green
    }
}
if (-not $bundleVerified) {
    Write-Error "Verification failed: 'ru' not found in bundle files!"
    exit 1
}

$idx = [System.IO.File]::ReadAllText($indexHtmlPath, [System.Text.Encoding]::UTF8)
$locMatches = [regex]::Matches($idx, [regex]::Escape("/localization/localization.js")).Count
if ($locMatches -ne 1) {
    Write-Error "Verification failed: index.html contains $locMatches localization injections (expected exactly 1)!"
    exit 1
}
Write-Host "      [OK] index.html contains exactly 1 localization injection (no duplicates)." -ForegroundColor Green

# Verify settings bundle contains language-default patch
$settingsVerified = $false
foreach ($sf in $settingsFiles) {
    $c = [System.IO.File]::ReadAllText($sf.FullName, [System.Text.Encoding]::UTF8)
    if ($c.Contains('localStorage.getItem(`i18nextLng`)') -or $c.Contains('localStorage.getItem("i18nextLng")')) {
        $settingsVerified = $true
        Write-Host "      [OK] Settings bundle $($sf.Name) contains dynamic language-default handler." -ForegroundColor Green
    }
}
if (-not $settingsVerified) {
    Write-Error "Verification failed: language-default handler not found in settings bundles!"
    exit 1
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "     RUSSIAN LOCALIZATION SUCCESSFULLY INSTALLED AND ACTIVE" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan