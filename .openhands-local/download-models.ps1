# OpenHands Nexus - Interactive Model Downloader
# Downloads quantized local AI models directly into proper directories with resume support.
[CmdletBinding()]
param(
    [string]$Preset = "", # "solo", "triad", "flagship", "voice", "all"
    [switch]$NonInteractive
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "OpenHands Nexus - Загрузка локальных AI моделей"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ModelsDir = Join-Path $ProjectRoot "Models"

function Show-Header {
    Clear-Host
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "         OPENHANDS NEXUS - МЕНЕДЖЕР ЗАГРУЗКИ AI МОДЕЛЕЙ" -ForegroundColor Cyan
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Download-ModelFile([string]$Url, [string]$DestPath, [string]$DisplayName, [double]$ExpectedGb) {
    $parent = Split-Path -Parent $DestPath
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }

    if (Test-Path $DestPath) {
        $existingGb = [math]::Round((Get-Item $DestPath).Length / 1GB, 2)
        if ($existingGb -ge ($ExpectedGb * 0.95)) {
            Write-Host "  [OK] $DisplayName уже скачан (${existingGb} GB): $DestPath" -ForegroundColor Green
            return
        } else {
            Write-Host "  [!] $DisplayName найден не полностью (${existingGb} / ~${ExpectedGb} GB). Возобновление загрузки..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [+] Загрузка: $DisplayName (~${ExpectedGb} GB)..." -ForegroundColor Cyan
    }

    Write-Host "      URL: $Url" -ForegroundColor Gray
    Write-Host "      Цель: $DestPath" -ForegroundColor Gray

    # Use curl with resume support (-C -), follow redirects (-L), and progress bar (#)
    $curlCmd = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curlCmd) {
        # Quick HTTP check
        $headOut = & curl.exe -sI -L --max-time 10 $Url
        $isOk = $headOut | Where-Object { $_ -match "HTTP/\S+\s+200" }
        if (-not $isOk) {
            Write-Host "      [WARN] Удалённый файл недоступен или требует авторизации (HTTP 401/404)." -ForegroundColor Yellow
            Write-Host "             Если веса хранятся локально, скопируйте файл вручную в:" -ForegroundColor Gray
            Write-Host "             $DestPath" -ForegroundColor White
            Write-Host ""
            return
        }
        & curl.exe -L -C - --retry 5 --retry-delay 3 --max-time 14400 -# -o $DestPath $Url
    } else {
        # Fallback to BITS or Invoke-WebRequest
        Start-BitsTransfer -Source $Url -Destination $DestPath -DisplayName "Download $DisplayName"
    }

    if (Test-Path $DestPath) {
        $finalGb = [math]::Round((Get-Item $DestPath).Length / 1GB, 2)
        Write-Host "      [ГОТОВО] Скачано: ${finalGb} GB" -ForegroundColor Green
    } else {
        Write-Host "      [ОШИБКА] Не удалось загрузить $DisplayName" -ForegroundColor Red
    }
    Write-Host ""
}

# Catalog of verified models and HuggingFace mirrors
$Catalog = @{
    gigaam = @{
        Name = "FUTO GigaAM v3 e2e-rnnt (STT)"
        Path = Join-Path $ModelsDir "Speech\gigaam-v3-e2e-rnnt-Q8_0.gguf"
        SizeGb = 0.26
        Url = "https://huggingface.co/cstr/gigaam-v3-GGUF/resolve/main/gigaam-v3-e2e-rnnt-q8_0.gguf"
    }

    ornith = @{
        Name = "Ornith 1.5 Coder 35B ICE (MTP)"
        Path = Join-Path $ModelsDir "Ornith\Ornith-1.5-35B-MTP-19G-ICE.gguf"
        SizeGb = 17.53
        Url = "https://huggingface.co/Alexperowo/Ornith-1.5-35B-MTP-ICE-GGUF/resolve/main/Ornith-1.5-35B-MTP-19G-ICE.gguf"
    }
    qwen27_base = @{
        Name = "Qwen 3.8 27B Opus Distill (Base Q4_K_M)"
        Path = Join-Path $ModelsDir "Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
        SizeGb = 15.66
        Url = "https://huggingface.co/Alexperowo/Qwen3.8-27B-Opus-Distill-v2-GGUF/resolve/main/Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
    }
    qwen27_mmproj = @{
        Name = "Qwen 3.8 Multimodal Vision Projector (f16)"
        Path = Join-Path $ModelsDir "Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf"
        SizeGb = 0.86
        Url = "https://huggingface.co/Alexperowo/Qwen3.8-27B-Opus-Distill-v2-GGUF/resolve/main/Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf"
    }
    qwen122 = @{
        Name = "Qwen 3.5 122B A10B LynnStyle (MoE Flagship)"
        Path = Join-Path $ModelsDir "Qwen-122b\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf"
        SizeGb = 44.12
        Url = "https://huggingface.co/Alexperowo/Qwen3.5-122B-A10B-LynnStyle-GGUF/resolve/main/Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf"
    }
    qwen80_next = @{
        Name = "Qwen3-Next 80B Thinking UD (Q3_K_XL)"
        Path = Join-Path $ModelsDir "Qwen3-Next\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf"
        SizeGb = 33.06
        Url = "https://huggingface.co/Alexperowo/Qwen3-Next-80B-A3B-Thinking-GGUF/resolve/main/Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf"
    }
}

function Run-Preset([string]$p) {
    switch ($p.ToLower()) {
        "voice" {
            Write-Host ">>> Загрузка голосовых моделей STT..." -ForegroundColor Cyan
            Download-ModelFile $Catalog.gigaam.Url $Catalog.gigaam.Path $Catalog.gigaam.Name $Catalog.gigaam.SizeGb
        }
        "solo" {
            Write-Host ">>> Пресет: Быстрый старт (Ornith 35B Coder + Голос)..." -ForegroundColor Cyan
            Download-ModelFile $Catalog.gigaam.Url $Catalog.gigaam.Path $Catalog.gigaam.Name $Catalog.gigaam.SizeGb
            Download-ModelFile $Catalog.ornith.Url $Catalog.ornith.Path $Catalog.ornith.Name $Catalog.ornith.SizeGb
        }
        "triad" {
            Write-Host ">>> Пресет: Полная Триада (Qwen 27B + Ornith 35B + Голос)..." -ForegroundColor Cyan
            Download-ModelFile $Catalog.gigaam.Url $Catalog.gigaam.Path $Catalog.gigaam.Name $Catalog.gigaam.SizeGb
            Download-ModelFile $Catalog.qwen27_base.Url $Catalog.qwen27_base.Path $Catalog.qwen27_base.Name $Catalog.qwen27_base.SizeGb
            Download-ModelFile $Catalog.qwen27_mmproj.Url $Catalog.qwen27_mmproj.Path $Catalog.qwen27_mmproj.Name $Catalog.qwen27_mmproj.SizeGb
            Download-ModelFile $Catalog.ornith.Url $Catalog.ornith.Path $Catalog.ornith.Name $Catalog.ornith.SizeGb
        }
        "flagship" {
            Write-Host ">>> Пресет: Флагманский супер-инженер (Qwen 122B + Триада)..." -ForegroundColor Cyan
            Download-ModelFile $Catalog.gigaam.Url $Catalog.gigaam.Path $Catalog.gigaam.Name $Catalog.gigaam.SizeGb
            Download-ModelFile $Catalog.qwen27_base.Url $Catalog.qwen27_base.Path $Catalog.qwen27_base.Name $Catalog.qwen27_base.SizeGb
            Download-ModelFile $Catalog.qwen27_mmproj.Url $Catalog.qwen27_mmproj.Path $Catalog.qwen27_mmproj.Name $Catalog.qwen27_mmproj.SizeGb
            Download-ModelFile $Catalog.ornith.Url $Catalog.ornith.Path $Catalog.ornith.Name $Catalog.ornith.SizeGb
            Download-ModelFile $Catalog.qwen122.Url $Catalog.qwen122.Path $Catalog.qwen122.Name $Catalog.qwen122.SizeGb
        }
        "all" {
            Write-Host ">>> Пресет: Полный флот (Все модели станции)..." -ForegroundColor Cyan
            foreach ($k in $Catalog.Keys) {
                $item = $Catalog[$k]
                Download-ModelFile $item.Url $item.Path $item.Name $item.SizeGb
            }
        }
        default {
            Write-Host "Неизвестный пресет: $p" -ForegroundColor Red
        }
    }
}

if ($Preset) {
    Run-Preset $Preset
    exit 0
}

# Interactive Menu
while ($true) {
    Show-Header
    Write-Host "Текущее состояние папки моделей ($ModelsDir):" -ForegroundColor Yellow
    foreach ($k in $Catalog.Keys) {
        $item = $Catalog[$k]
        if (Test-Path $item.Path) {
            $sz = [math]::Round((Get-Item $item.Path).Length / 1GB, 2)
            Write-Host ("  [OK  ] {0,-36} : {1,6} GB" -f $item.Name, $sz) -ForegroundColor Green
        } else {
            Write-Host ("  [MISS] {0,-36} : {1,6} GB (не скачан)" -f $item.Name, $item.SizeGb) -ForegroundColor Gray
        }
    }
    Write-Host ""
    Write-Host "Выберите комплект для загрузки:" -ForegroundColor White
    Write-Host "  [1] Быстрый старт:  Ornith 1.5 35B Coder + FUTO GigaAM v3 (~18 GB)" -ForegroundColor Cyan
    Write-Host "  [2] Полная Триада:  Qwen 3.8 27B + Ornith 35B + GigaAM (~34 GB)" -ForegroundColor Cyan
    Write-Host "  [3] Флагман MoE:    Qwen 3.5 122B LynnStyle + Триада (~78 GB)" -ForegroundColor Cyan
    Write-Host "  [4] Только голос:   FUTO GigaAM v3 STT (~260 MB)" -ForegroundColor Cyan
    Write-Host "  [5] Полный флот:    Все доступные модели станции (~111 GB)" -ForegroundColor Cyan
    Write-Host "  [0] Выход" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "Ваш выбор [0-5]"
    switch ($choice) {
        "1" { Run-Preset "solo"; pause }
        "2" { Run-Preset "triad"; pause }
        "3" { Run-Preset "flagship"; pause }
        "4" { Run-Preset "voice"; pause }
        "5" { Run-Preset "all"; pause }
        "0" { exit 0 }
        default { Write-Host "Неверный ввод. Нажмите Enter..." -ForegroundColor Red; Start-Sleep -Seconds 1 }
    }
}
