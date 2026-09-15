# OpenHands Nexus - Quad-Dump Static Prefix Cache Generator & Manager
# Creates and warms the 4 canonical NVMe slot dumps:
# 1. architect_prefix.bin (Qwen 122B - Lead Architect / Planner)
# 2. executor_prefix.bin (Ornith 35B - Fast Coder / Implementer)
# 3. auditor_prefix.bin (Qwen 80B / 27B - Auditor / Reviewer)
# 4. solo_full_prefix.bin (Qwen 122B / 27B - Solo Autonomous Full Stack)

param(
    [string]$Action = "status", # status, generate, restore, clean
    [string]$Role = "all",     # all, architect, executor, auditor, solo
    [string]$RouterUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$ProjectRootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$CacheDir = Join-Path $ProjectRootDir "Cache\slots"

if (-not (Test-Path $CacheDir)) {
    New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
}

$Dumps = @{
    "architect" = @{
        "filename" = "architect_prefix.bin"
        "model" = "qwen122"
        "role_title" = "Lead Architect & Planner (Qwen 122B)"
        "desc" = "Архитектор: системный промпт, чтение файлов, планирование, делегирование (без file_editor)"
    }
    "executor" = @{
        "filename" = "executor_prefix.bin"
        "model" = "ornith"
        "role_title" = "Code Executor & Tester (Ornith 35B)"
        "desc" = "Исполнитель: синтез кода, редактирование файлов (file_editor), терминал и запуск тестов"
    }
    "auditor" = @{
        "filename" = "auditor_prefix.bin"
        "model" = "next"
        "role_title" = "Security & Code Auditor (Qwen 80B)"
        "desc" = "Аудитор: глубокий анализ кода, безопасность, верификация тестов, поиск краевых случаев"
    }
    "solo" = @{
        "filename" = "solo_full_prefix.bin"
        "model" = "qwen122"
        "role_title" = "Solo Autonomous Developer (Qwen 122B)"
        "desc" = "Автономный соло-инженер: полный набор инструментов, архитектура, код и терминал в одной модели"
    }
}

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "       OPENHANDS NEXUS - QUAD-DUMP STATIC PREFIX CACHE" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Каталог NVMe кэша: $CacheDir" -ForegroundColor Gray
Write-Host ""

function Show-Status {
    Write-Host "Текущее состояние 4 префиксных дампов (NVMe Cache):" -ForegroundColor Yellow
    Write-Host "---------------------------------------------------------------------" -ForegroundColor DarkGray
    foreach ($key in @("architect", "executor", "auditor", "solo")) {
        $info = $Dumps[$key]
        $filePath = Join-Path $CacheDir $info.filename
        $exists = Test-Path $filePath
        if ($exists) {
            $item = Get-Item $filePath
            $sizeMB = [math]::Round($item.Length / 1MB, 2)
            $date = $item.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
            Write-Host "  [✓ ГОТОВ] " -ForegroundColor Green -NoNewline
            Write-Host "$($info.role_title) " -ForegroundColor White -NoNewline
            Write-Host "($($info.filename), $sizeMB MB, $date)" -ForegroundColor Gray
        } else {
            Write-Host "  [✕ НЕТ]   " -ForegroundColor Red -NoNewline
            Write-Host "$($info.role_title) " -ForegroundColor White -NoNewline
            Write-Host "($($info.filename) отсутствует)" -ForegroundColor DarkGray
        }
        Write-Host "            Назначение: $($info.desc)" -ForegroundColor DarkCyan
    }
    Write-Host "---------------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "Команда генерации: .\generate-prefix-dumps.ps1 -Action generate" -ForegroundColor Yellow
}

function Generate-Dump([string]$dumpKey) {
    $info = $Dumps[$dumpKey]
    if (-not $info) {
        Write-Warning "Неизвестный ключ дампа: $dumpKey"
        return
    }

    $filePath = Join-Path $CacheDir $info.filename
    Write-Host "[*] Подготовка дампа для: $($info.role_title)..." -ForegroundColor Cyan
    Write-Host "    Файл: $($info.filename)" -ForegroundColor Gray
    Write-Host "    Целевая модель llama-swap: $($info.model)" -ForegroundColor Gray

    # Test router connectivity
    try {
        $models = Invoke-RestMethod -Uri "$RouterUrl/v1/models" -TimeoutSec 3 -ErrorAction Stop
    } catch {
        Write-Host "[WARN] llama-swap на $RouterUrl недоступен. Запустите openhands.ps1 start" -ForegroundColor Yellow
        return
    }

    # Construct role prefix payload
    $rolePrompt = switch ($dumpKey) {
        "architect" {
            "OpenHands Nexus Lead Architect: You are the planning lead. You analyze requirements, inspect files, formulate architectures, and delegate implementation via switch_llm. You do not modify code directly."
        }
        "executor" {
            "OpenHands Nexus Code Executor: You implement software features, edit files, run bash commands, execute test suites, and report results back to the architect."
        }
        "auditor" {
            "OpenHands Nexus Code & Security Auditor: You perform comprehensive code review, find regressions, test edge cases, and verify architectural compliance."
        }
        "solo" {
            "OpenHands Nexus Solo Autonomous Engineer: You have full autonomy to plan, edit files, execute tests, and complete complex software engineering objectives."
        }
    }

    $reqBody = @{
        "model" = $info.model
        "messages" = @(
            @{ "role" = "system"; "content" = $rolePrompt },
            @{ "role" = "user"; "content" = "Initialize role slot prefix. Output 'READY'." }
        )
        "max_tokens" = 2
        "temperature" = 0.0
    } | ConvertTo-Json -Depth 5

    Write-Host "    Отправка префикса в модель $($info.model)..." -ForegroundColor Gray
    try {
        $resp = Invoke-RestMethod -Uri "$RouterUrl/v1/chat/completions" -Method Post -Body $reqBody -ContentType "application/json; charset=utf-8" -TimeoutSec 300
        Write-Host "    [OK] Префикс обработан моделью: $($resp.choices[0].message.content.Trim())" -ForegroundColor Green
        
        # Find active llama-server process port
        $llamaPort = $null
        $proc = Get-Process llama-server -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($proc) {
            $conn = Get-NetTCPConnection -State Listen -OwningProcess $proc.Id -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($conn) {
                $llamaPort = $conn.LocalPort
            }
        }

        if (-not $llamaPort) {
            Write-Host "    [WARN] Не удалось определить порт активного llama-server." -ForegroundColor Yellow
            return
        }

        # Save slot to NVMe cache
        $saveUrl = "http://127.0.0.1:$llamaPort/slots/0?action=save"
        Write-Host "    Сохранение слота в NVMe кэш через порт $($llamaPort): $($info.filename)..." -ForegroundColor Gray
        $saveBody = @{ filename = $info.filename } | ConvertTo-Json
        $saveResp = Invoke-RestMethod -Uri $saveUrl -Method Post -Body $saveBody -ContentType "application/json; charset=utf-8" -TimeoutSec 30
        $sizeMB = [math]::Round($saveResp.n_written / 1MB, 2)
        Write-Host "    [OK] Статический префикс сохранен: $($info.filename) ($($saveResp.n_saved) токенов, $sizeMB MB, $($saveResp.timings.save_ms) ms)." -ForegroundColor Green
    } catch {
        Write-Host "    [WARN] Ошибка при генерации/сохранении префикса: $_" -ForegroundColor Yellow
    }
}

switch ($Action.ToLower()) {
    "status" {
        Show-Status
    }
    "generate" {
        if ($Role -eq "all") {
            foreach ($k in @("architect", "executor", "auditor", "solo")) {
                Generate-Dump $k
            }
        } else {
            Generate-Dump $Role
        }
        Write-Host ""
        Show-Status
    }
    "clean" {
        Write-Host "[*] Очистка кэша слотов..." -ForegroundColor Yellow
        Remove-Item (Join-Path $CacheDir "*") -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Кэш слотов очищен." -ForegroundColor Green
        Show-Status
    }
    default {
        Show-Status
    }
}
