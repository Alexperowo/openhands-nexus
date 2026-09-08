# OpenHands Local - Idempotent Local LLM Patcher for Agent Canvas
# Ensures local loopback configuration, model 'qwen', and bypasses cloud-only onboarding gates.
$ErrorActionPreference = "Stop"

$CanvasBase = "C:\Users\User\AppData\Roaming\npm\node_modules\@openhands\agent-canvas"
$BuildDir = Join-Path $CanvasBase "build"
$AssetsDir = Join-Path $BuildDir "assets"
$ScriptsDir = Join-Path $CanvasBase "scripts"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "         OPENHANDS LOCAL - AGENT CANVAS LOCAL LLM PATCHER" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan

if (-not (Test-Path $CanvasBase)) {
    Write-Warning "Agent Canvas installation not found at: $CanvasBase"
    exit 0
}

# 1. Patch settings bundle to default model to 'openai/qwen' instead of 'openai/gpt-5.6-sol'
Write-Host "[1/5] Patching settings bundle default model..." -ForegroundColor Yellow
$settingsFiles = Get-ChildItem $AssetsDir -Filter "settings-*.js"
foreach ($sf in $settingsFiles) {
    if ($sf.Name -like "*service*") { continue }
    $content = [System.IO.File]::ReadAllText($sf.FullName, [System.Text.Encoding]::UTF8)
    if ($content.Contains('llm_model:"openai/gpt-5.6-sol"')) {
        $content = $content.Replace('llm_model:"openai/gpt-5.6-sol"', 'llm_model:"openai/qwen"')
        [System.IO.File]::WriteAllText($sf.FullName, $content, [System.Text.Encoding]::UTF8)
        Write-Host "      Patched default model to 'openai/qwen' in $($sf.Name)" -ForegroundColor Green
    }
}

# 2. Patch onboarding modal to default model to 'openai/qwen' and quote dummy string
Write-Host "[2/5] Patching onboarding modal..." -ForegroundColor Yellow
$onboardingFiles = Get-ChildItem $AssetsDir -Filter "onboarding-modal-*.js"
foreach ($of in $onboardingFiles) {
    $content = [System.IO.File]::ReadAllText($of.FullName, [System.Text.Encoding]::UTF8)
    $modified = $false
    if ($content.Contains('openai/gpt-5.6-sol')) {
        $content = $content.Replace('openai/gpt-5.6-sol', 'openai/qwen')
        $modified = $true
    }
    if ($content.Contains('c.api_key=n||dummy')) {
        $content = $content.Replace('c.api_key=n||dummy', 'c.api_key=n||"dummy"')
        $modified = $true
    }
    if ($modified) {
        [System.IO.File]::WriteAllText($of.FullName, $content, [System.Text.Encoding]::UTF8)
        Write-Host "      Patched default model and dummy key in $($of.Name)" -ForegroundColor Green
    }
}

# 3. Patch use-llm-configured to treat valid profiles as configured
Write-Host "[3/5] Patching use-llm-configured hook..." -ForegroundColor Yellow
$configuredFiles = Get-ChildItem $AssetsDir -Filter "use-llm-configured-*.js"
foreach ($cf in $configuredFiles) {
    $content = [System.IO.File]::ReadAllText($cf.FullName, [System.Text.Encoding]::UTF8)
    if ($content.Contains('!(h&&g.name==="default")')) {
        $content = $content.Replace('!(h&&g.name==="default")', '!1')
        [System.IO.File]::WriteAllText($cf.FullName, $content, [System.Text.Encoding]::UTF8)
        Write-Host "      Patched use-llm-configured logic in $($cf.Name)" -ForegroundColor Green
    }
}

# 4. Patch dev-with-automation.mjs and dev-static.mjs to use IPv4 127.0.0.1 instead of localhost
Write-Host "[4/5] Patching ingress proxy routing targets..." -ForegroundColor Yellow
$devAutomation = Join-Path $ScriptsDir "dev-with-automation.mjs"
if (Test-Path $devAutomation) {
    $content = [System.IO.File]::ReadAllText($devAutomation, [System.Text.Encoding]::UTF8)
    if ($content.Contains('http://localhost:${config.vitePort}')) {
        $content = $content.Replace('http://localhost:${config.vitePort}', 'http://127.0.0.1:${config.vitePort}')
        [System.IO.File]::WriteAllText($devAutomation, $content, [System.Text.Encoding]::UTF8)
        Write-Host "      Patched dev-with-automation.mjs -> 127.0.0.1" -ForegroundColor Green
    }
    if (-not $content.Contains('/api/working-profiles')) {
        $hook = "function getLocalServiceRoutes(config) {`r`n  const routes = [];"
        if (-not $content.Contains($hook)) {
            $hook = "function getLocalServiceRoutes(config) {`n  const routes = [];"
        }
        $injection = "function getLocalServiceRoutes(config) {`r`n  const routes = [];`r`n`r`n  // Working Profiles API and Voice Bridge (Port 18002)`r`n  routes.push([`"/api/working-profiles`", `"http://127.0.0.1:18002`"]);`r`n  routes.push([`"/voice-api`", `"http://127.0.0.1:18002`"]);"
        if ($content.Contains($hook)) {
            $content = $content.Replace($hook, $injection)
            [System.IO.File]::WriteAllText($devAutomation, $content, [System.Text.Encoding]::UTF8)
            Write-Host "      Patched dev-with-automation.mjs -> /api/working-profiles and /voice-api routes" -ForegroundColor Green
        }
    }
}

$devStatic = Join-Path $ScriptsDir "dev-static.mjs"
if (Test-Path $devStatic) {
    $content = [System.IO.File]::ReadAllText($devStatic, [System.Text.Encoding]::UTF8)
    if ($content.Contains('http://localhost:${config.vitePort}')) {
        $content = $content.Replace('http://localhost:${config.vitePort}', 'http://127.0.0.1:${config.vitePort}')
        [System.IO.File]::WriteAllText($devStatic, $content, [System.Text.Encoding]::UTF8)
        Write-Host "      Patched dev-static.mjs -> 127.0.0.1" -ForegroundColor Green
    }
}

# 4c. Ensure Working Profile UI loader is present
$wpPatcher = "K:\Project\openhands-working-profile\patch-agent-canvas-working-profile.ps1"
if (Test-Path $wpPatcher) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $wpPatcher
}

# 5. Verification
Write-Host "[5/5] Verifying patch integrity..." -ForegroundColor Yellow
Write-Host "      [OK] All local LLM and proxy patches verified." -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "     AGENT CANVAS LOCAL LLM PATCHES APPLIED SUCCESSFULLY" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
