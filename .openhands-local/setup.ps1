# OpenHands Local — Initial Setup & Portability Alignment Script
[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [switch]$AutoFix,
    [switch]$SkipFirewall,
    [switch]$StartAfterSetup
)

$Host.UI.RawUI.WindowTitle = "OpenHands Local — Первичная настройка и инициализация"
$ErrorActionPreference = "Continue"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "       OPENHANDS NEXUS — ПЕРВИЧНАЯ НАСТРОЙКА И КОНФИГУРАЦИЯ" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$openhandsHome = Join-Path $userHome ".openhands"
$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $userHome 'AppData\Roaming' }

# 1. Align llama-swap config to current project root
Write-Host "[1/6] Синхронизация путей llama-swap/config.yaml..." -ForegroundColor Yellow
$cfgPath = Join-Path $ProjectRoot "llama-swap\config.yaml"
if (Test-Path $cfgPath) {
    try {
        $cText = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8)
        $pattern = '[a-zA-Z]:\\[^\s"'']+\\(ik_llama|Models|llama-mainline)'
        $replacement = $ProjectRoot + '\$1'
        $aligned = [regex]::Replace($cText, $pattern, $replacement)
        if ($aligned -ne $cText) {
            [System.IO.File]::WriteAllText($cfgPath, $aligned, [System.Text.Encoding]::UTF8)
            Write-Host "      [OK] Пути в llama-swap/config.yaml обновлены под текущий каталог: $ProjectRoot" -ForegroundColor Green
        } else {
            Write-Host "      [OK] Пути в llama-swap/config.yaml уже соответствуют текущему каталогу." -ForegroundColor Gray
        }
    } catch {
        Write-Host "      [WARN] Ошибка синхронизации config.yaml: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "      [WARN] Файл $cfgPath не найден." -ForegroundColor Yellow
}
Write-Host ""

# 2. Initialize %USERPROFILE%\.openhands directory structure and settings
Write-Host "[2/6] Инициализация пользовательского окружения OpenHands..." -ForegroundColor Yellow
if (-not (Test-Path $openhandsHome)) {
    New-Item -ItemType Directory -Path $openhandsHome -Force | Out-Null
    Write-Host "      [OK] Создан каталог: $openhandsHome" -ForegroundColor Green
}

# 2a. Profiles directory
$profilesDir = Join-Path $openhandsHome "profiles"
if (-not (Test-Path $profilesDir)) { New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null }
$existingProfiles = @(Get-ChildItem $profilesDir -Filter "*.json" -ErrorAction SilentlyContinue)
if ($existingProfiles.Count -eq 0) {
    $defaultsProfilesDir = Join-Path $ProjectRoot "Config\defaults\profiles"
    if (Test-Path $defaultsProfilesDir) {
        Copy-Item -Path (Join-Path $defaultsProfilesDir "*.json") -Destination $profilesDir -Force
        $cnt = (Get-ChildItem $profilesDir -Filter "*.json").Count
        Write-Host "      [OK] Развернуты профили OpenHands из Config/defaults/profiles ($cnt шт.)" -ForegroundColor Green
    }
} else {
    Write-Host "      [OK] Профили OpenHands уже присутствуют ($($existingProfiles.Count) шт.)" -ForegroundColor Gray
}

# 2b. Working Profiles directory
$wpDir = Join-Path $openhandsHome "working-profiles"
if (-not (Test-Path $wpDir)) { New-Item -ItemType Directory -Path $wpDir -Force | Out-Null }
$existingWp = @(Get-ChildItem $wpDir -Filter "*.json" -ErrorAction SilentlyContinue)
if ($existingWp.Count -eq 0) {
    $wpTemplatesDir = Join-Path $ProjectRoot "Config\working-profile-templates"
    if (Test-Path $wpTemplatesDir) {
        Copy-Item -Path (Join-Path $wpTemplatesDir "*.json") -Destination $wpDir -Force
        $cnt = (Get-ChildItem $wpDir -Filter "*.json").Count
        Write-Host "      [OK] Развернуты шаблоны Working Profiles ($cnt шт.)" -ForegroundColor Green
    }
} else {
    Write-Host "      [OK] Шаблоны Working Profiles уже присутствуют ($($existingWp.Count) шт.)" -ForegroundColor Gray
}

# 2c. Working profile active state
$wpStateFile = Join-Path $openhandsHome "working-profile-state.json"
if (-not (Test-Path $wpStateFile)) {
    $initState = @{
        active_working_profile = "team-full"
        reasoning_mode = "standard_team"
        last_switched_at = (Get-Date -Format "o")
        switched_by = "setup_init"
    } | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($wpStateFile, $initState, [System.Text.Encoding]::UTF8)
    Write-Host "      [OK] Инициализирован активный профиль по умолчанию: team-full" -ForegroundColor Green
} else {
    Write-Host "      [OK] Активный профиль уже сохранен в working-profile-state.json" -ForegroundColor Gray
}

# 2d. Settings.json (seed or align MCP paths)
$settingsFile = Join-Path $openhandsHome "settings.json"
$templateSettingsFile = Join-Path $ProjectRoot "Config\defaults\settings.template.json"
if (-not (Test-Path $settingsFile) -and (Test-Path $templateSettingsFile)) {
    $sContent = [System.IO.File]::ReadAllText($templateSettingsFile, [System.Text.Encoding]::UTF8)
    $escapedRoot = $ProjectRoot.Replace('\', '\\')
    $sContent = $sContent.Replace('{{PROJECT_ROOT}}', $escapedRoot)
    [System.IO.File]::WriteAllText($settingsFile, $sContent, [System.Text.Encoding]::UTF8)
    Write-Host "      [OK] Развернут settings.json с локальной конфигурацией LLM и Android MCP" -ForegroundColor Green
} elseif (Test-Path $settingsFile) {
    try {
        $sContent = [System.IO.File]::ReadAllText($settingsFile, [System.Text.Encoding]::UTF8)
        $mcpPattern = '"args":\s*\[\s*"[A-Za-z]:\\[^"\r\n]*?\\android-mcp\\dist\\index\.js"\s*\]'
        $escapedRoot = $ProjectRoot.Replace('\', '\\')
        $newMcpArg = "`"args`": [ `"$escapedRoot\\\\android-mcp\\\\dist\\\\index.js`" ]"
        $sUpdated = [regex]::Replace($sContent, $mcpPattern, $newMcpArg)
        if ($sUpdated -ne $sContent) {
            [System.IO.File]::WriteAllText($settingsFile, $sUpdated, [System.Text.Encoding]::UTF8)
            Write-Host "      [OK] Обновлен путь android-mcp в settings.json: $ProjectRoot" -ForegroundColor Green
        } else {
            Write-Host "      [OK] Конфигурация settings.json актуальна." -ForegroundColor Gray
        }
    } catch {
        Write-Host "      [WARN] Ошибка обновления settings.json: $_" -ForegroundColor Yellow
    }
}
Write-Host ""

# 3. PWA TLS Certificates & SSL
Write-Host "[3/6] Проверка и генерация SSL-сертификатов PWA..." -ForegroundColor Yellow
$pfxPath = Join-Path $ProjectRoot "openhands-pwa\certs\openhands-lan.pfx"
$caPath = Join-Path $ProjectRoot "openhands-pwa\certs\openhands-ca.crt"
if (-not (Test-Path $pfxPath) -or -not (Test-Path $caPath)) {
    Write-Host "      Генерация локального Root CA и Leaf сертификатов для мобильного шлюза..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-pwa\generate-certs.ps1")
    if (Test-Path $pfxPath) {
        Write-Host "      [OK] SSL-сертификаты PWA успешно сгенерированы." -ForegroundColor Green
    } else {
        Write-Host "      [WARN] Не удалось сгенерировать SSL-сертификаты PWA." -ForegroundColor Yellow
    }
} else {
    Write-Host "      [OK] SSL-сертификаты PWA уже существуют и валидны." -ForegroundColor Gray
}
Write-Host ""

# 4. Windows Firewall Rule for Port 8443
Write-Host "[4/6] Настройка брандмауэра Windows для мобильного шлюза (порт 8443)..." -ForegroundColor Yellow
if (-not $SkipFirewall) {
    $fw = Get-NetFirewallRule -Name "OpenHands-LAN-PWA" -ErrorAction SilentlyContinue
    if (-not $fw) {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openhands-pwa\configure-firewall.ps1")
            Write-Host "      [OK] Правило брандмауэра Windows успешно добавлено." -ForegroundColor Green
        } catch {
            Write-Host "      [WARN] Для добавления правила брандмауэра требуются права администратора." -ForegroundColor Yellow
            Write-Host "             Запустите openhands-pwa\configure-firewall.ps1 от имени Администратора при необходимости подключения с мобильных устройств." -ForegroundColor Gray
        }
    } else {
        Write-Host "      [OK] Правило брандмауэра OpenHands-LAN-PWA активно." -ForegroundColor Gray
    }
} else {
    Write-Host "      [SKIP] Пропуск настройки брандмауэра по запросу (-SkipFirewall)." -ForegroundColor Gray
}
Write-Host ""

# 5. Apply Agent Canvas Idempotent Custom Layer Patches
Write-Host "[5/6] Применение патчей Custom Layer к Agent Canvas..." -ForegroundColor Yellow
$patchScripts = @(
    @{ Name = "Local LLM Defaults"; Path = Join-Path $ProjectRoot "openhands-localization\patch-agent-canvas-local-llm.ps1" },
    @{ Name = "Voice Bridge UI";    Path = Join-Path $ProjectRoot "local-voice\patch-agent-canvas-voice.ps1" },
    @{ Name = "Localization (RU)";  Path = Join-Path $ProjectRoot "openhands-localization\patch-agent-canvas-localization.ps1" },
    @{ Name = "Mobile PWA";         Path = Join-Path $ProjectRoot "openhands-pwa\patch-agent-canvas-pwa.ps1" },
    @{ Name = "Working Profile";    Path = Join-Path $ProjectRoot "openhands-working-profile\patch-agent-canvas-working-profile.ps1" }
)

foreach ($ps in $patchScripts) {
    if (Test-Path $ps.Path) {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $ps.Path | Out-Null
            Write-Host "      [OK] Патч '$($ps.Name)' применен." -ForegroundColor Green
        } catch {
            Write-Host "      [WARN] Ошибка применения патча '$($ps.Name)': $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "      [WARN] Скрипт патча не найден: $($ps.Path)" -ForegroundColor Yellow
    }
}
Write-Host ""

# 6. Verification and Final Report
Write-Host "[6/6] Итоговая проверка готовности системы..." -ForegroundColor Yellow
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check-dependencies.ps1")
$checkExit = $LASTEXITCODE

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
if ($checkExit -eq 0) {
    Write-Host "   НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНА: OpenHands Nexus готов к запуску!" -ForegroundColor Green
    Write-Host "   Для старта используйте: START-OPENHANDS-LOCAL.cmd" -ForegroundColor Cyan
    Write-Host "   Для планшетов и смартфонов: https://[LAN_IP]:8443" -ForegroundColor Cyan
} else {
    Write-Host "   НАСТРОЙКА ЗАВЕРШЕНА С ПРЕДУПРЕЖДЕНИЯМИ: Проверьте список выше." -ForegroundColor Yellow
}
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

if ($StartAfterSetup -and $checkExit -eq 0) {
    Write-Host "Запуск платформы (-StartAfterSetup)..." -ForegroundColor Green
    & (Join-Path $ProjectRoot "START-OPENHANDS-LOCAL.cmd")
}
