# OpenHands Nexus - Clean Windows 11 Automated Turnkey Installer
# Automatically provisions system runtimes via winget, Python AI libraries, Canvas stack, binaries, and configs.
[CmdletBinding()]
param(
    [switch]$SkipWinget,
    [switch]$SkipNpm,
    [switch]$SkipPip,
    [switch]$StartAfterInstall
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "OpenHands Nexus - Automated Turnkey Installer"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "     OPENHANDS NEXUS - CLEAN WINDOWS 11 TURNKEY INSTALLER" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target Root: $ProjectRoot" -ForegroundColor White
Write-Host ""

function Update-LocalEnvPath {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $sysPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
    $localAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }

    $extraPaths = @(
        "C:\Program Files\nodejs",
        (Join-Path $appData "npm"),
        (Join-Path $localAppData "Programs\Python\Python312"),
        (Join-Path $localAppData "Programs\Python\Python312\Scripts"),
        (Join-Path $localAppData "Programs\Python\Python311"),
        (Join-Path $localAppData "Programs\Python\Python311\Scripts"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        "C:\Program Files\Git\cmd",
        "C:\Program Files\Git\bin"
    )

    $allParts = ($extraPaths + ($userPath -split ';') + ($sysPath -split ';') + ($env:PATH -split ';')) | Select-Object -Unique | Where-Object { $_ -and (Test-Path $_) }
    $env:PATH = $allParts -join ';'
}

# 1. System Runtimes via Winget
if (-not $SkipWinget) {
    Write-Host "[1/5] Проверка и установка системных рантаймов (winget)..." -ForegroundColor Yellow

    $hasWinget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $hasWinget) {
        Write-Host "      [WARN] winget.exe не обнаружен. Убедитесь, что установлен 'App Installer' из Microsoft Store." -ForegroundColor Yellow
    } else {
        # Check Node.js
        $hasNode = Get-Command node.exe -ErrorAction SilentlyContinue
        if (-not $hasNode) {
            Write-Host "      Установка Node.js LTS via winget..." -ForegroundColor Cyan
            & winget install --id OpenJS.NodeJS.LTS -e --source winget --accept-package-agreements --accept-source-agreements --silent
        } else {
            Write-Host "      [OK] Node.js уже установлен: $(& node -v)" -ForegroundColor Green
        }

        # Check Python
        $hasPy = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $hasPy) {
            Write-Host "      Установка Python 3.12 via winget..." -ForegroundColor Cyan
            & winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements --silent
        } else {
            Write-Host "      [OK] Python уже установлен: $(& python --version)" -ForegroundColor Green
        }

        # Check Git
        $hasGit = Get-Command git.exe -ErrorAction SilentlyContinue
        if (-not $hasGit) {
            Write-Host "      Установка Git via winget..." -ForegroundColor Cyan
            & winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
        } else {
            Write-Host "      [OK] Git уже установлен: $(& git --version)" -ForegroundColor Green
        }

        # Check uv (Astral uv for openhands-agent-server)
        $hasUv = Get-Command uv.exe -ErrorAction SilentlyContinue
        if (-not $hasUv) {
            Write-Host "      Установка Astral uv via winget..." -ForegroundColor Cyan
            & winget install --id astral-sh.uv -e --source winget --accept-package-agreements --accept-source-agreements --silent
        } else {
            Write-Host "      [OK] Astral uv уже установлен: $(& uv --version)" -ForegroundColor Green
        }
    }
} else {
    Write-Host "[1/5] Пропуск установки winget (-SkipWinget)." -ForegroundColor Gray
}

Update-LocalEnvPath
Write-Host ""

# 2. Python AI & Speech Dependencies
if (-not $SkipPip) {
    Write-Host "[2/5] Установка библиотек Python для STT/TTS и тестов..." -ForegroundColor Yellow
    $pyCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $pkgs = @("cryptography", "av", "supertonic", "soundfile", "numpy", "uv")
        Write-Host "      Выполняется pip install $($pkgs -join ' ')..." -ForegroundColor Cyan
        & python -m pip install --quiet --upgrade pip
        & python -m pip install --quiet $pkgs
        Write-Host "      [OK] Python-зависимости успешно установлены." -ForegroundColor Green
    } else {
        Write-Host "      [FAIL] Python.exe не найден в PATH после обновления путей!" -ForegroundColor Red
    }
} else {
    Write-Host "[2/5] Пропуск pip install (-SkipPip)." -ForegroundColor Gray
}
Write-Host ""

# 3. OpenHands Agent Canvas
if (-not $SkipNpm) {
    Write-Host "[3/5] Установка OpenHands Agent Canvas CLI..." -ForegroundColor Yellow
    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCmd) {
        $canvasCheck = Get-Command agent-canvas.cmd -ErrorAction SilentlyContinue
        if (-not $canvasCheck) {
            Write-Host "      Выполняется npm install -g @openhands/agent-canvas..." -ForegroundColor Cyan
            & npm install -g @openhands/agent-canvas
            Write-Host "      [OK] @openhands/agent-canvas установлен глобально." -ForegroundColor Green
        } else {
            Write-Host "      [OK] Agent Canvas уже установлен глобально." -ForegroundColor Green
        }
    } else {
        Write-Host "      [FAIL] npm.cmd не найден в PATH!" -ForegroundColor Red
    }
} else {
    Write-Host "[3/5] Пропуск установки Canvas (-SkipNpm)." -ForegroundColor Gray
}
Write-Host ""

# 4. Binaries Extraction / Verification
Write-Host "[4/5] Развёртывание исполняемых бинарников инференса..." -ForegroundColor Yellow
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup-binaries.ps1")
Write-Host ""

# 5. Station Configuration & Custom Layer Patches
Write-Host "[5/5] Применение конфигураций, mTLS сертификатов и патчей Nexus..." -ForegroundColor Yellow
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup.ps1")
Write-Host ""

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "       УСТАНОВКА И ПЕРВИЧНАЯ НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНЫ!" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor White
Write-Host "1. Скачать необходимые модели:   DOWNLOAD-MODELS.cmd" -ForegroundColor Yellow
Write-Host "2. Запустить рабочую станцию:    START-OPENHANDS-LOCAL.cmd" -ForegroundColor Green
Write-Host "3. Проверить состояние системы:  CHECK-DEPENDENCIES.cmd" -ForegroundColor Cyan
Write-Host ""

if ($StartAfterInstall) {
    Write-Host "Запуск станции (-StartAfterInstall)..." -ForegroundColor Green
    & (Join-Path $ProjectRoot "START-OPENHANDS-LOCAL.cmd")
}
