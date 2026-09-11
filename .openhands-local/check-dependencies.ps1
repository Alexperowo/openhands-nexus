# OpenHands Local — System Dependency & Portability Checker
$Host.UI.RawUI.WindowTitle = "OpenHands Local — Проверка системных зависимостей"
$ErrorActionPreference = "Continue"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "         OPENHANDS NEXUS — ПРОВЕРКА СИСТЕМНЫХ ЗАВИСИМОСТЕЙ" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Global:TotalChecks = 0
$Global:PassedChecks = 0
$Global:WarningChecks = 0
$Global:ErrorChecks = 0

function Report-Item([string]$Title, [string]$Status, [string]$Details) {
    $Global:TotalChecks++
    $fgColor = "Gray"
    $detailColor = "White"
    if ($Status -eq "OK") {
        $Global:PassedChecks++
        $fgColor = "Green"
        $detailColor = "Gray"
    } elseif ($Status -eq "WARN") {
        $Global:WarningChecks++
        $fgColor = "Yellow"
        $detailColor = "Yellow"
    } elseif ($Status -eq "FAIL") {
        $Global:ErrorChecks++
        $fgColor = "Red"
        $detailColor = "Red"
    }

    Write-Host ("  [{0,-4}] " -f $Status) -NoNewline -ForegroundColor $fgColor
    Write-Host (" {0,-32} : " -f $Title) -NoNewline -ForegroundColor White
    Write-Host $Details -ForegroundColor $detailColor
}

# 1. OS & PowerShell
Write-Host "[1/8] Операционная система и среда выполнения:" -ForegroundColor Yellow
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os -and [int]$os.BuildNumber -ge 22000) {
    Report-Item "Windows 11" "OK" "$($os.Caption) (Build $($os.BuildNumber))"
} elseif ($os) {
    Report-Item "Windows Version" "WARN" "$($os.Caption) (Build $($os.BuildNumber)) — рекомендуется Windows 11 Build 22000+"
} else {
    Report-Item "Windows Version" "WARN" "Не удалось определить сборку ОС через WMI"
}

$psVer = $PSVersionTable.PSVersion
if ($psVer.Major -ge 5) {
    Report-Item "PowerShell" "OK" "Версия $($psVer.ToString())"
} else {
    Report-Item "PowerShell" "FAIL" "Версия $($psVer.ToString()) (требуется >= 5.1)"
}
Write-Host ""

# 2. Core Runtimes
Write-Host "[2/8] Базовые среды выполнения (Node, Python, Git):" -ForegroundColor Yellow
try {
    $nodeVer = (& node -v 2>$null)
    if ($nodeVer) { $nodeVer = $nodeVer.Trim() }
    if ($nodeVer -match '^v(\d+)\.') {
        $major = [int]$Matches[1]
        if ($major -ge 18) {
            Report-Item "Node.js" "OK" "$nodeVer (требуется >= 18)"
        } else {
            Report-Item "Node.js" "FAIL" "$nodeVer (устаревшая версия, требуется >= 18)"
        }
    } else {
        Report-Item "Node.js" "FAIL" "Не найден в PATH"
    }
} catch {
    Report-Item "Node.js" "FAIL" "Ошибка вызова node"
}

try {
    $pyVer = (& python --version 2>$null)
    if ($pyVer) { $pyVer = $pyVer.Trim() }
    if ($pyVer -match 'Python\s+(\d+)\.(\d+)') {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        if ($maj -eq 3 -and $min -ge 10) {
            Report-Item "Python" "OK" "$pyVer (требуется >= 3.10)"
        } else {
            Report-Item "Python" "FAIL" "$pyVer (требуется >= 3.10)"
        }
    } else {
        Report-Item "Python" "FAIL" "Не найден в PATH"
    }
} catch {
    Report-Item "Python" "FAIL" "Ошибка вызова python"
}

try {
    $gitVer = (& git --version 2>$null)
    if ($gitVer) {
        Report-Item "Git" "OK" "$($gitVer.Trim())"
    } else {
        Report-Item "Git" "WARN" "Git не обнаружен в PATH"
    }
} catch {
    Report-Item "Git" "WARN" "Ошибка вызова git"
}
Write-Host ""

# 3. Python Speech & AI Packages
Write-Host "[3/8] Библиотеки Python (Voice, Audio, Crypto):" -ForegroundColor Yellow
$pyPkgs = @('cryptography', 'av', 'supertonic', 'soundfile', 'numpy')
foreach ($pkg in $pyPkgs) {
    $checkRes = (& python -c "import $pkg; print(getattr($pkg, '__version__', 'installed'))" 2>$null)
    if ($checkRes) { $checkRes = $checkRes.Trim() }
    if ($LASTEXITCODE -eq 0 -and $checkRes) {
        Report-Item "Python: $pkg" "OK" "v$checkRes"
    } else {
        Report-Item "Python: $pkg" "FAIL" "Не установлен (pip install $pkg)"
    }
}
$dllPath = Join-Path $ProjectRoot "transcribe-build-shared\bin\Release\transcribe.dll"
$pyCmd = "import sys, os; os.environ['TRANSCRIBE_LIBRARY']=r'$dllPath'; sys.path.insert(0, r'$ProjectRoot\local-voice'); import transcribe_cpp; print(transcribe_cpp.__version__)"
$transRes = (& python -c $pyCmd 2>$null)
if ($transRes) { $transRes = $transRes.Trim() }
if ($LASTEXITCODE -eq 0 -and $transRes) {
    Report-Item "transcribe_cpp (GigaAM)" "OK" "v$transRes (local-voice package)"
} else {
    Report-Item "transcribe_cpp (GigaAM)" "WARN" "Не загружен из local-voice\transcribe_cpp"
}
Write-Host ""

# 4. Hardware GPU & CUDA
Write-Host "[4/8] Аппаратное ускорение (NVIDIA GPU / CUDA):" -ForegroundColor Yellow
try {
    $smiLines = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null)
    if ($smiLines) {
        $totalVramMb = 0
        $gpuIndex = 0
        foreach ($line in $smiLines) {
            $trimmed = $line.Trim()
            if (-not $trimmed) { continue }
            $parts = $trimmed -split ',\s*'
            $gpuName = $parts[0]
            $vram = $parts[1]
            $driver = $parts[2]
            Report-Item "NVIDIA GPU #$gpuIndex" "OK" "$gpuName ($vram, Driver $driver)"
            if ($vram -match '(\d+)\s*MiB') {
                $totalVramMb += [int]$Matches[1]
            }
            $gpuIndex++
        }

        $totalGb = [math]::Round($totalVramMb / 1024, 1)
        if ($totalVramMb -ge 35000) {
            Report-Item "VRAM Pool (Total)" "OK" "${totalGb} GB across $gpuIndex GPUs (достаточно для Team-Full 3-моделей + Qwen3-Next 80B Multi-GPU)"
        } elseif ($totalVramMb -ge 20000) {
            Report-Item "VRAM Pool (Total)" "OK" "${totalGb} GB (достаточно для Team-Full 3-моделей)"
        } elseif ($totalVramMb -ge 12000) {
            Report-Item "VRAM Pool (Total)" "WARN" "${totalGb} GB (рекомендуется >= 20 GB для Team-Full; одиночные профили работают)"
        } else {
            Report-Item "VRAM Pool (Total)" "WARN" "${totalGb} GB (меньше 12 GB; возможен offload в RAM)"
        }
    } else {
        Report-Item "NVIDIA GPU" "WARN" "nvidia-smi не обнаружен (CUDA ускорение недоступно)"
    }
} catch {
    Report-Item "NVIDIA GPU" "WARN" "Ошибка опроса nvidia-smi"
}
Write-Host ""

# 5. OpenHands Platform & Canvas Patches
Write-Host "[5/8] Платформа OpenHands Agent Canvas и патчи:" -ForegroundColor Yellow
$canvasCmd = Get-Command agent-canvas.cmd -ErrorAction SilentlyContinue
if ($canvasCmd) {
    Report-Item "Agent Canvas CLI" "OK" "$($canvasCmd.Source)"
} else {
    $appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
    $candCanvas = Join-Path $appData "npm\agent-canvas.cmd"
    if (Test-Path $candCanvas) {
        Report-Item "Agent Canvas CLI" "OK" "$candCanvas"
    } else {
        Report-Item "Agent Canvas CLI" "WARN" "agent-canvas.cmd не найден в PATH / npm"
    }
}

# Check Canvas patched build
$appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData\Roaming' }
$canvasBuildDir = Join-Path $appData "npm\node_modules\@openhands\agent-canvas\build"
$indexHtml = Join-Path $canvasBuildDir "index.html"
if (Test-Path $indexHtml) {
    $hContent = Get-Content $indexHtml -Raw -Encoding UTF8
    
    # 1. Localization
    $locBundle = Join-Path $canvasBuildDir "locales\ru\openhands.json"
    $hasLoc = (Test-Path $locBundle)
    $locSt = if ($hasLoc) { "OK" } else { "FAIL" }
    $locDt = if ($hasLoc) { "Активен (ru/openhands.json)" } else { "Не применен" }
    Report-Item "Patch: Localization" $locSt $locDt

    # 2. Voice Bridge
    $voiceFile = Join-Path $canvasBuildDir "voice\voice-bridge.js"
    $hasVoice = (Test-Path $voiceFile) -or ($hContent -match 'voice-bridge|oh-voice-loader')
    $vSt = if ($hasVoice) { "OK" } else { "FAIL" }
    $vDt = if ($hasVoice) { "Активен (STT + TTS)" } else { "Не применен" }
    Report-Item "Patch: Voice Bridge" $vSt $vDt

    # 3. Working Profile
    $wpFile = Join-Path $canvasBuildDir "working-profile\working-profile-ui.js"
    $hasProfile = (Test-Path $wpFile) -or ($hContent -match 'working-profile-ui')
    $wpSt = if ($hasProfile) { "OK" } else { "FAIL" }
    $wpDt = if ($hasProfile) { "Активен (селектор профилей)" } else { "Не применен" }
    Report-Item "Patch: Working Profile" $wpSt $wpDt

    # 4. PWA Mobile
    $pwaManifest = Join-Path $canvasBuildDir "manifest.webmanifest"
    $hasPwa = (Test-Path $pwaManifest) -and ($hContent -match 'manifest\.webmanifest')
    $pwaSt = if ($hasPwa) { "OK" } else { "FAIL" }
    $pwaDt = if ($hasPwa) { "Активен (manifest.webmanifest + mobile-pwa.css)" } else { "Не применен" }
    Report-Item "Patch: PWA Mobile" $pwaSt $pwaDt
} else {
    Report-Item "Canvas Build" "WARN" "Файл $indexHtml не найден"
}
Write-Host ""

# 6. Local AI Models Inventory
Write-Host "[6/8] Локальные модели искусственного интеллекта:" -ForegroundColor Yellow
$modelsToCheck = @(
    @{ Name = "Qwen 3.8 Opus (Base)"; Path = Join-Path $ProjectRoot "Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" },
    @{ Name = "Qwen 3.8 Multimodal"; Path = Join-Path $ProjectRoot "Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf" },
    @{ Name = "Ornith 1.5 Coder 35B"; Path = Join-Path $ProjectRoot "Models\Ornith\Ornith-1.5-35B-MTP-19G-ICE.gguf" },
    @{ Name = "Qwen3-Next 80B Thinking"; Path = Join-Path $ProjectRoot "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf" },
    @{ Name = "Qwen3-Next Draft MTP"; Path = Join-Path $ProjectRoot "Models\Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf" },
    @{ Name = "FUTO GigaAM v3 STT"; Path = Join-Path $ProjectRoot "Models\Speech\gigaam-v3-e2e-rnnt-Q8_0.gguf" },
    @{ Name = "Supertonic 3 TTS"; Path = Join-Path $ProjectRoot "Models\Speech\supertonic" }
)

foreach ($m in $modelsToCheck) {
    if (Test-Path $m.Path) {
        $sz = if (Test-Path -PathType Container $m.Path) {
            $sum = (Get-ChildItem $m.Path -Recurse | Measure-Object -Property Length -Sum).Sum
            "{0:N1} MB" -f ($sum / 1MB)
        } else {
            "{0:N2} GB" -f ((Get-Item $m.Path).Length / 1GB)
        }
        Report-Item $m.Name "OK" "$sz ($($m.Path))"
    } else {
        Report-Item $m.Name "WARN" "Отсутствует: $($m.Path)"
    }
}
Write-Host ""

# 7. Network & PWA Security
Write-Host "[7/8] Сеть, PWA и SSL-сертификаты:" -ForegroundColor Yellow
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
if ($lanIp) {
    Report-Item "LAN IPv4" "OK" "$lanIp (доступен для планшетов и смартфонов)"
} else {
    Report-Item "LAN IPv4" "WARN" "Внешний IPv4 не обнаружен (только localhost)"
}

$certPfx = Join-Path $ProjectRoot "openhands-pwa\certs\openhands-lan.pfx"
$certCa = Join-Path $ProjectRoot "openhands-pwa\certs\openhands-ca.crt"
if ((Test-Path $certPfx) -and (Test-Path $certCa)) {
    Report-Item "PWA SSL Certificates" "OK" "Root CA и Leaf PFX сертификаты готовы"
} else {
    Report-Item "PWA SSL Certificates" "WARN" "Сертификаты еще не сгенерированы (будут созданы при setup)"
}

# Firewall rule
$fw = Get-NetFirewallRule -Name "OpenHands-LAN-PWA" -ErrorAction SilentlyContinue
if ($fw -and $fw.Enabled -eq "True") {
    Report-Item "Firewall Rule (8443)" "OK" "Правило OpenHands-LAN-PWA активно"
} else {
    Report-Item "Firewall Rule (8443)" "WARN" "Правило брандмауэра для порта 8443 не настроено"
}
Write-Host ""

# 8. Network Ports
Write-Host "[8/8] Статус сетевых портов платформы:" -ForegroundColor Yellow
$ports = @(
    @{ Port = 8000; Service = "Agent Canvas Ingress" },
    @{ Port = 8080; Service = "Local LLM Router (llama-swap)" },
    @{ Port = 8443; Service = "Mobile LAN PWA Gateway (HTTPS)" },
    @{ Port = 18000; Service = "OpenHands Agent Server" },
    @{ Port = 18001; Service = "OpenHands Automation" },
    @{ Port = 18002; Service = "Local Voice Bridge & Profiles API" }
)

foreach ($item in $ports) {
    $p = $item.Port
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pName = (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Report-Item "Порт $p [$($item.Service)]" "OK" "Активен (PID $($conn.OwningProcess) — $pName)"
    } else {
        Report-Item "Порт $p [$($item.Service)]" "OK" "Свободен (готов к запуску)"
    }
}
Write-Host ""

$summaryColor = if ($Global:ErrorChecks -eq 0) { "Green" } else { "Red" }
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ("ИТОГ ПРОВЕРКИ: Проверок: {0} | Успешно: {1} | Предупреждений: {2} | Ошибок: {3}" -f $Global:TotalChecks, $Global:PassedChecks, $Global:WarningChecks, $Global:ErrorChecks) -ForegroundColor $summaryColor
Write-Host "=====================================================================" -ForegroundColor Cyan

if ($Global:ErrorChecks -gt 0) {
    Write-Host "[!] Обнаружены критические ошибки. Запустите SETUP-OPENHANDS-LOCAL.cmd для исправления." -ForegroundColor Red
    exit 1
} else {
    Write-Host "[OK] Все критические зависимости и компоненты готовы к работе." -ForegroundColor Green
    exit 0
}
