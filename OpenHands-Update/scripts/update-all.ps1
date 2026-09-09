# OpenHands Local Platform - Central Update Dashboard & Orchestrator
# Location: K:\Project\OpenHands-Update\scripts\update-all.ps1

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

# Canonical Centralized Logs
$LogDir = Join-Path $Global:ProjectRootDir "Logs\Updater"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "update-all-$ts.log"

function Log-Output([string]$msg, [string]$level = "INFO") {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $formatted = "[$now] [$level] $msg"
    switch ($level) {
        "ERROR"   { Write-Host $formatted -ForegroundColor Red }
        "WARN"    { Write-Host $formatted -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $formatted -ForegroundColor Green }
        "STEP"    { Write-Host $formatted -ForegroundColor Cyan }
        default   { Write-Host $formatted -ForegroundColor White }
    }
    Add-Content -Path $LogFile -Value $formatted -Encoding UTF8 -ErrorAction SilentlyContinue
}

# 1. Enforce Safe Default Invocation
if (-not $CheckOnly -and -not $DryRun) {
    Log-Output "No execution mode specified. Defaulting safely to -CheckOnly." "INFO"
    $CheckOnly = $true
}

# 2. Check Station Status
$ports = @(8000, 8080, 18000, 18001, 18002)
$activeConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
$stationRunning = ($activeConns.Count -gt 0)
$stationStatusStr = if ($stationRunning) { "RUNNING (Ports: $(($activeConns.LocalPort | Select-Object -Unique) -join ', '))" } else { "STOPPED (All ports free)" }

Log-Output "=====================================================================" "STEP"
Log-Output "               OPENHANDS LOCAL - UPDATE DASHBOARD" "STEP"
Log-Output "=====================================================================" "STEP"
Log-Output "Platform Status: $stationStatusStr" "INFO"
Log-Output ""

# 3. Query Component Statuses
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$headers = @{ "User-Agent" = "OpenHands-Update-Station/1.0" }

$results = [System.Collections.Generic.List[PSObject]]::new()

# Component 1: llama-swap
$swapCurrent = "unknown"
$swapBin = Join-Path $Global:ProjectRootDir "llama-swap\bin\llama-swap.exe"
if (Test-Path $swapBin) {
    try {
        $raw = & $swapBin -version 2>&1
        if ($raw -match "v\d+") { $swapCurrent = $Matches[0] }
    } catch {}
}
$swapLatest = "unknown"
try {
    $res = Invoke-RestMethod -Uri "https://api.github.com/repos/mostlygeek/llama-swap/releases/latest" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
    $swapLatest = $res.tag_name
} catch {
    # Fallback to HTML scraping
    try {
        $rawHtml = [string]::Join("`n", (curl.exe -s -L --max-time 10 "https://github.com/mostlygeek/llama-swap/releases"))
        if ($rawHtml -match '/mostlygeek/llama-swap/releases/tag/(v\d+)') {
            $swapLatest = $Matches[1]
        }
    } catch {}
}
$swapStatus = if ($swapCurrent -eq $swapLatest) { "UP TO DATE" } else { "UPDATE AVAILABLE" }
$results.Add([PSCustomObject]@{
    Component     = "llama-swap"
    Current       = $swapCurrent
    Latest        = $swapLatest
    Status        = $swapStatus
    UpdaterReady  = "READY (update-llama-swap.ps1)"
})

# Component 2: llama-mainline
$mainlineCurrent = "unknown"
$manifestPath = Join-Path $Global:ProjectRootDir "Config\backend-versions.json"
if (Test-Path $manifestPath) {
    try {
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.llama_mainline.build) { $mainlineCurrent = $manifest.llama_mainline.build }
    } catch {}
}
if ($mainlineCurrent -eq "unknown") {
    $mainlineDir = Get-ChildItem -Path (Join-Path $Global:ProjectRootDir "llama-mainline") -Directory -Filter "b*" -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($mainlineDir) { $mainlineCurrent = $mainlineDir.Name }
}
$mainlineBin = Join-Path $Global:ProjectRootDir "llama-mainline\$mainlineCurrent\llama-server.exe"
if (Test-Path $mainlineBin) {
    try {
        $raw = & $mainlineBin --version 2>&1
        if ($raw -match "build\s+(\d+)") { $mainlineCurrent = "b$($Matches[1])" }
    } catch {}
}
$mainlineLatest = "unknown"
try {
    $rawHtml = [string]::Join("`n", (curl.exe -s --max-time 10 "https://github.com/ggml-org/llama.cpp/releases"))
    if ($rawHtml -match '/ggml-org/llama\.cpp/releases/tag/(b\d+)') {
        $mainlineLatest = $Matches[1]
    }
} catch {}
if ($mainlineLatest -eq "unknown") {
    try {
        $res = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
        $mainlineLatest = $res[0].tag_name
    } catch {}
}
$mainlineStatus = if ($mainlineCurrent -eq $mainlineLatest) { "UP TO DATE" } else { "UPDATE AVAILABLE" }
$results.Add([PSCustomObject]@{
    Component     = "llama-mainline"
    Current       = $mainlineCurrent
    Latest        = $mainlineLatest
    Status        = $mainlineStatus
    UpdaterReady  = "READY (update-llama-mainline.ps1)"
})

# Component 3: ik_llama
$ikCurrent = "3c58ae3"
$ikBin = Join-Path $Global:ProjectRootDir "ik_llama\bin\llama-server.exe"
if (Test-Path $ikBin) {
    try {
        $raw = & $ikBin --version 2>&1
        if ($raw -match "\(([a-f0-9]{7})\)") { $ikCurrent = $Matches[1] }
    } catch {}
}
$ikLatest = "fe215a8"
try {
    $commits = Invoke-RestMethod -Uri "https://api.github.com/repos/ikawrakow/ik_llama.cpp/commits?per_page=1" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
    if ($commits -and $commits.Count -gt 0) {
        $ikLatest = $commits[0].sha.Substring(0, 7)
    }
} catch {
    # Fallback to HTML commit scraping if rate-limited
    try {
        $rawHtml = [string]::Join("`n", (curl.exe -s --max-time 10 "https://github.com/ikawrakow/ik_llama.cpp/commits/master"))
        if ($rawHtml -match '/ikawrakow/ik_llama\.cpp/commit/([a-f0-9]{7})') {
            $ikLatest = $Matches[1]
        }
    } catch {}
}
$ikStatus = if ($ikCurrent -eq $ikLatest) { "UP TO DATE" } else { "UPDATE AVAILABLE" }
$results.Add([PSCustomObject]@{
    Component     = "ik_llama"
    Current       = $ikCurrent
    Latest        = $ikLatest
    Status        = $ikStatus
    UpdaterReady  = "READY (update-ik-llama.ps1)"
})

# Component 4: @openhands/agent-canvas
$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$canvasPkg = Join-Path $appData "npm\node_modules\@openhands\agent-canvas\package.json"
$canvasCurrent = "unknown"
if (Test-Path $canvasPkg) {
    try {
        $canvasCurrent = "v" + (Get-Content $canvasPkg -Raw | ConvertFrom-Json).version
    } catch {}
}
$canvasLatest = "unknown"
try {
    $verOut = & cmd.exe /c "npm view @openhands/agent-canvas version 2>nul"
    if ($LASTEXITCODE -eq 0 -and $verOut) { $canvasLatest = "v" + $verOut.Trim() }
} catch {}
$canvasStatus = if ($canvasCurrent -eq $canvasLatest) { "UP TO DATE" } else { "UPDATE AVAILABLE" }
$results.Add([PSCustomObject]@{
    Component     = "@openhands/agent-canvas"
    Current       = $canvasCurrent
    Latest        = $canvasLatest
    Status        = $canvasStatus
    UpdaterReady  = "READY (update-openhands.ps1)"
})

# Component 5: openhands-agent-server
$defsJson = Join-Path $appData "npm\node_modules\@openhands\agent-canvas\config\defaults.json"
$serverPinned = "unknown"
$automationPinned = "unknown"
if (Test-Path $defsJson) {
    try {
        $defs = Get-Content $defsJson -Raw | ConvertFrom-Json
        $serverPinned = "v" + $defs.versions.agentServer
        $automationPinned = "v" + $defs.versions.automation
    } catch {}
}
$serverPyPi = "unknown"
try {
    $res = Invoke-RestMethod -Uri "https://pypi.org/pypi/openhands-agent-server/json" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
    $serverPyPi = "v" + $res.info.version
} catch {}
$serverStatus = if ($serverPinned -eq $serverPyPi) { "UP TO DATE" } else { "PINNED (PyPI: $serverPyPi)" }
$results.Add([PSCustomObject]@{
    Component     = "openhands-agent-server"
    Current       = $serverPinned
    Latest        = $serverPyPi
    Status        = $serverStatus
    UpdaterReady  = "MANAGED_VIA_CANVAS"
})

# Component 6: openhands-automation
$automationPyPi = "unknown"
try {
    $res = Invoke-RestMethod -Uri "https://pypi.org/pypi/openhands-automation/json" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
    $automationPyPi = "v" + $res.info.version
} catch {}
$automationStatus = if ($automationPinned -eq $automationPyPi) { "UP TO DATE" } else { "PINNED (PyPI: $automationPyPi)" }
$results.Add([PSCustomObject]@{
    Component     = "openhands-automation"
    Current       = $automationPinned
    Latest        = $automationPyPi
    Status        = $automationStatus
    UpdaterReady  = "MANAGED_VIA_CANVAS"
})

# Display Compact Matrix
Write-Host ""
$results | Format-Table -AutoSize | Out-String | ForEach-Object { Log-Output $_.TrimEnd() "INFO" }
Write-Host ""

Log-Output "=====================================================================" "STEP"
Log-Output "                      UPDATE POLICY & GUIDANCE" "STEP"
Log-Output "=====================================================================" "STEP"
Log-Output "1. Component updates are strictly decoupled to preserve rollback boundaries." "INFO"
Log-Output "2. Auto-promotion of multiple components in a single batch is DISABLED." "INFO"
Log-Output "3. To update an individual component, use its dedicated updater script:" "INFO"
Log-Output "     - llama-swap:          .\update-llama-swap.ps1 -Update -TargetVersion latest" "INFO"
Log-Output "     - llama-mainline:      .\update-llama-mainline.ps1 -Update -TargetBuild latest" "INFO"
Log-Output "     - ik_llama:            .\update-ik-llama.ps1" "INFO"
Log-Output "     - OpenHands App Stack: .\update-openhands.ps1 -Update -TargetVersion latest" "INFO"
Log-Output "=====================================================================" "STEP"

exit 0
