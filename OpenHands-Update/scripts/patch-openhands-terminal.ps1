# OpenHands Terminal Auto-Recovery Patcher
# Location: K:\Project\OpenHands-Update\scripts\patch-openhands-terminal.ps1
# Ensures PowerShell session automatically revives if killed by Ctrl+Break/C-c/crash.

[CmdletBinding()]
param(
    [switch]$Rollback
)

$ErrorActionPreference = "Stop"
$uvCache = Join-Path $env:LOCALAPPDATA "uv\cache\archive-v0"

if (-not (Test-Path $uvCache)) {
    Write-Host "[Terminal Patcher] UV cache not found at: $uvCache. Skipping." -ForegroundColor Yellow
    exit 0
}

$targetFiles = Get-ChildItem -Path (Join-Path $uvCache "*\Lib\site-packages\openhands\tools\terminal\terminal\windows_terminal.py") -File -ErrorAction SilentlyContinue

if (-not $targetFiles -or $targetFiles.Count -eq 0) {
    Write-Host "[Terminal Patcher] No windows_terminal.py found in UV cache." -ForegroundColor Yellow
    exit 0
}

foreach ($item in $targetFiles) {
    $filePath = $item.FullName
    $backupPath = "$filePath.orig"

    if ($Rollback) {
        if (Test-Path $backupPath) {
            Copy-Item $backupPath $filePath -Force
            Remove-Item $backupPath -Force
            Write-Host "[Terminal Patcher] Rolled back: $filePath" -ForegroundColor Green
        }
        continue
    }

    # Backup if not exists
    if (-not (Test-Path $backupPath)) {
        Copy-Item $filePath $backupPath -Force
        Write-Host "[Terminal Patcher] Created backup: $backupPath" -ForegroundColor Gray
    }

    $content = [System.IO.File]::ReadAllText($filePath, [System.Text.Encoding]::UTF8)

    $targetPattern = 'if self\.process is None or self\.process\.poll\(\) is not None:\s+raise RuntimeError\("Cannot send keys: PowerShell process is not running"\)'
    $replacement = @"
if self.process is None or self.process.poll() is not None:
            logger.info("PowerShell process exited, auto-recovering shell session...")
            self._initialized = False
            self.initialize()
"@

    if ($content -match $targetPattern) {
        $patched = [regex]::Replace($content, $targetPattern, $replacement)
        [System.IO.File]::WriteAllText($filePath, $patched, [System.Text.Encoding]::UTF8)
        Write-Host "[Terminal Patcher] Patched auto-recovery in: $filePath" -ForegroundColor Green
    } elseif ($content -match 'auto-recovering shell session') {
        Write-Host "[Terminal Patcher] Already patched: $filePath" -ForegroundColor Gray
    } else {
        Write-Host "[Terminal Patcher] Pattern not found in: $filePath" -ForegroundColor Yellow
    }
}
