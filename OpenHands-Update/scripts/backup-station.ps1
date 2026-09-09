# OpenHands Local — Station Backup Generator
[CmdletBinding()]
param(
    [string]$BackupName = "",
    [switch]$IncludeModels,
    [switch]$CreateZip
)

$Host.UI.RawUI.WindowTitle = "OpenHands Local — Резервное копирование станции"
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"
Init-UpdaterLog "station-backup"

Log-Msg "=====================================================================" "STEP"
Log-Msg "          OPENHANDS NEXUS — РЕЗЕРВНОЕ КОПИРОВАНИЕ СТАНЦИИ" "STEP"
Log-Msg "=====================================================================" "STEP"

$ProjectRoot = $Global:ProjectRootDir
$stationBackupDir = Join-Path $Global:ProjectRootDir "Archive\backups\station"
if (-not (Test-Path $stationBackupDir)) { New-Item -ItemType Directory -Path $stationBackupDir -Force | Out-Null }

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$folderName = if ($BackupName) { "backup-$BackupName-$ts" } else { "station-backup-$ts" }
$targetBackupFolder = Join-Path $stationBackupDir $folderName
New-Item -ItemType Directory -Path $targetBackupFolder -Force | Out-Null

Log-Msg "Целевой каталог резервной копии: $targetBackupFolder" "INFO"

# 1. Backup Config
Log-Msg "[1/5] Резервное копирование Config/..." "INFO"
$dstConfig = Join-Path $targetBackupFolder "Config"
Fast-CopyDir (Join-Path $ProjectRoot "Config") $dstConfig

# 2. Backup llama-swap configs and scripts
Log-Msg "[2/5] Резервное копирование llama-swap конфигурации..." "INFO"
$dstSwap = Join-Path $targetBackupFolder "llama-swap"
New-Item -ItemType Directory -Path $dstSwap -Force | Out-Null
foreach ($f in @("config.yaml", "start-swap.ps1", "stop-swap.ps1", "START-LLAMA-SWAP.cmd", "STOP-LLAMA-SWAP.cmd")) {
    $srcFile = Join-Path $ProjectRoot "llama-swap\$f"
    if (Test-Path $srcFile) { Copy-Item $srcFile $dstSwap -Force }
}

# 3. Backup openhands-pwa certs and gateway
Log-Msg "[3/5] Резервное копирование PWA и SSL-сертификатов..." "INFO"
$dstPwa = Join-Path $targetBackupFolder "openhands-pwa"
Fast-CopyDir (Join-Path $ProjectRoot "openhands-pwa") $dstPwa

# 4. Backup Custom Layer sources and root launchers
Log-Msg "[4/5] Резервное копирование Custom Layer и скриптов запуска..." "INFO"
Fast-CopyDir (Join-Path $ProjectRoot "local-voice") (Join-Path $targetBackupFolder "local-voice")
Fast-CopyDir (Join-Path $ProjectRoot "openhands-localization") (Join-Path $targetBackupFolder "openhands-localization")
Fast-CopyDir (Join-Path $ProjectRoot "openhands-working-profile") (Join-Path $targetBackupFolder "openhands-working-profile")
Fast-CopyDir (Join-Path $ProjectRoot ".openhands-local") (Join-Path $targetBackupFolder ".openhands-local")

# Root cmd files
$dstRootCmd = Join-Path $targetBackupFolder "root-launchers"
New-Item -ItemType Directory -Path $dstRootCmd -Force | Out-Null
Get-ChildItem -Path $ProjectRoot -Filter "*.cmd" | ForEach-Object {
    Copy-Item $_.FullName $dstRootCmd -Force
}

# 5. Backup User State from %USERPROFILE%\.openhands
Log-Msg "[5/5] Резервное копирование состояния пользователя (%USERPROFILE%\.openhands)..." "INFO"
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$srcUserOpenHands = Join-Path $userHome ".openhands"
$dstUserState = Join-Path $targetBackupFolder "user-openhands"
New-Item -ItemType Directory -Path $dstUserState -Force | Out-Null

if (Test-Path $srcUserOpenHands) {
    if (Test-Path (Join-Path $srcUserOpenHands "profiles")) {
        Fast-CopyDir (Join-Path $srcUserOpenHands "profiles") (Join-Path $dstUserState "profiles")
    }
    if (Test-Path (Join-Path $srcUserOpenHands "working-profiles")) {
        Fast-CopyDir (Join-Path $srcUserOpenHands "working-profiles") (Join-Path $dstUserState "working-profiles")
    }
    foreach ($uf in @("working-profile-state.json", "settings.json")) {
        $uPath = Join-Path $srcUserOpenHands $uf
        if (Test-Path $uPath) { Copy-Item $uPath $dstUserState -Force }
    }
    $apiKeyPath = Join-Path $srcUserOpenHands "agent-canvas\api-key.txt"
    if (Test-Path $apiKeyPath) {
        $dstAk = Join-Path $dstUserState "agent-canvas"
        New-Item -ItemType Directory -Path $dstAk -Force | Out-Null
        Copy-Item $apiKeyPath $dstAk -Force
    }
}

# 6. Optional Models backup
if ($IncludeModels) {
    Log-Msg "Включение моделей в бэкап (-IncludeModels)..." "WARN"
    Fast-CopyDir (Join-Path $ProjectRoot "Models") (Join-Path $targetBackupFolder "Models")
}

# 7. Write Manifest
$manifest = @{
    backup_type = "OpenHands-Nexus-Station"
    created_at = (Get-Date -Format "o")
    computer_name = $env:COMPUTERNAME
    user_name = $env:USERNAME
    source_root = $ProjectRoot
    include_models = [bool]$IncludeModels
    files_count = (Get-ChildItem -Path $targetBackupFolder -Recurse -File).Count
    total_bytes = (Get-ChildItem -Path $targetBackupFolder -Recurse -File | Measure-Object -Property Length -Sum).Sum
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $targetBackupFolder "BACKUP_MANIFEST.json") -Encoding UTF8

# Optional Zip
if ($CreateZip) {
    Log-Msg "Создание ZIP-архива..." "STEP"
    $zipFile = "$targetBackupFolder.zip"
    Compress-Archive -Path "$targetBackupFolder\*" -DestinationPath $zipFile -Force
    Log-Msg "Архив создан: $zipFile" "SUCCESS"
}

Log-Msg "=====================================================================" "SUCCESS"
Log-Msg "Резервная копия успешно создана!" "SUCCESS"
Log-Msg "Расположение: $targetBackupFolder" "SUCCESS"
Log-Msg "Файлов: $($manifest.files_count) | Объем: $('{0:N2} MB' -f ($manifest.total_bytes / 1MB))" "SUCCESS"
Log-Msg "=====================================================================" "SUCCESS"
