# OpenHands Local — Station Restore Script
[CmdletBinding()]
param(
    [string]$BackupPath = "",
    [switch]$RestartPlatform,
    [switch]$Force
)

$Host.UI.RawUI.WindowTitle = "OpenHands Local — Восстановление станции"
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "station-restore"

Log-Msg "=====================================================================" "WARN"
Log-Msg "          OPENHANDS NEXUS — ВОССТАНОВЛЕНИЕ СТАНЦИИ" "WARN"
Log-Msg "=====================================================================" "WARN"

$ProjectRoot = $Global:ProjectRootDir
$stationBackupDir = Join-Path $Global:ProjectRootDir "Archive\backups\station"

if (-not $BackupPath) {
    if (Test-Path $stationBackupDir) {
        $backups = Get-ChildItem -Path $stationBackupDir -Directory | Sort-Object CreationTime -Descending
        if ($backups.Count -gt 0) {
            $BackupPath = $backups[0].FullName
            Log-Msg "Автоматически выбрана последняя резервная копия: $BackupPath" "INFO"
        }
    }
}

if (-not $BackupPath -or -not (Test-Path $BackupPath)) {
    Log-Msg "Резервная копия не найдена по пути: $BackupPath" "ERROR"
    exit 1
}

$manifestFile = Join-Path $BackupPath "BACKUP_MANIFEST.json"
if (Test-Path $manifestFile) {
    $man = Get-Content $manifestFile -Raw | ConvertFrom-Json
    Log-Msg "Информация о копии: Создана $($man.created_at) на ПК $($man.computer_name)" "INFO"
}

# 1. Stop active platform
Log-Msg "[1/5] Остановка работающих сервисов платформы..." "STEP"
& (Join-Path $ProjectRoot ".openhands-local\stop.ps1")
Start-Sleep -Seconds 2

# 2. Restore Config
Log-Msg "[2/5] Восстановление конфигурации Config/ и llama-swap..." "STEP"
$srcConfig = Join-Path $BackupPath "Config"
if (Test-Path $srcConfig) {
    Fast-CopyDir $srcConfig (Join-Path $ProjectRoot "Config")
}

$srcSwap = Join-Path $BackupPath "llama-swap"
if (Test-Path $srcSwap) {
    foreach ($f in Get-ChildItem -Path $srcSwap -File) {
        Copy-Item $f.FullName (Join-Path $ProjectRoot "llama-swap") -Force
    }
}

# 3. Restore PWA and certs
Log-Msg "[3/5] Восстановление PWA и SSL-сертификатов..." "STEP"
$srcPwa = Join-Path $BackupPath "openhands-pwa"
if (Test-Path $srcPwa) {
    Fast-CopyDir $srcPwa (Join-Path $ProjectRoot "openhands-pwa")
}

# 4. Restore Custom Layer
Log-Msg "[4/5] Восстановление исходных компонентов Custom Layer..." "STEP"
foreach ($dir in @("local-voice", "openhands-localization", "openhands-working-profile", ".openhands-local")) {
    $src = Join-Path $BackupPath $dir
    if (Test-Path $src) {
        Fast-CopyDir $src (Join-Path $ProjectRoot $dir)
    }
}

# 5. Restore User State to %USERPROFILE%\.openhands
Log-Msg "[5/5] Восстановление состояния пользователя (%USERPROFILE%\.openhands)..." "STEP"
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$dstUserOpenHands = Join-Path $userHome ".openhands"
$srcUserState = Join-Path $BackupPath "user-openhands"

if (Test-Path $srcUserState) {
    if (-not (Test-Path $dstUserOpenHands)) { New-Item -ItemType Directory -Path $dstUserOpenHands -Force | Out-Null }
    
    $srcProfiles = Join-Path $srcUserState "profiles"
    if (Test-Path $srcProfiles) {
        Fast-CopyDir $srcProfiles (Join-Path $dstUserOpenHands "profiles")
    }
    
    $srcWp = Join-Path $srcUserState "working-profiles"
    if (Test-Path $srcWp) {
        Fast-CopyDir $srcWp (Join-Path $dstUserOpenHands "working-profiles")
    }

    foreach ($uf in @("working-profile-state.json", "settings.json")) {
        $uPath = Join-Path $srcUserState $uf
        if (Test-Path $uPath) { Copy-Item $uPath $dstUserOpenHands -Force }
    }

    $srcAk = Join-Path $srcUserState "agent-canvas\api-key.txt"
    if (Test-Path $srcAk) {
        $dstAk = Join-Path $dstUserOpenHands "agent-canvas"
        New-Item -ItemType Directory -Path $dstAk -Force | Out-Null
        Copy-Item $srcAk $dstAk -Force
    }
}

# 6. Run setup to re-align paths and re-apply patches
Log-Msg "Выравнивание путей и повторное наложение патчей Agent Canvas..." "STEP"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot ".openhands-local\setup.ps1")

Log-Msg "=====================================================================" "SUCCESS"
Log-Msg "Восстановление станции успешно завершено!" "SUCCESS"
Log-Msg "=====================================================================" "SUCCESS"

if ($RestartPlatform) {
    Log-Msg "Запуск платформы (-RestartPlatform)..." "STEP"
    & (Join-Path $ProjectRoot "START-OPENHANDS-LOCAL.cmd")
}
