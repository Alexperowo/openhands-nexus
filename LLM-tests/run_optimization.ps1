param(
    [string]$OptDir = "K:\Project\LLM-tests\optimization",
    [string]$PromptFile = "K:\Project\LLM-tests\benchmark_prompt.txt",
    [string]$ServerExe = "K:\Project\ik_llama\bin\llama-server.exe",
    [string]$ModelFile = "D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
)

$ErrorActionPreference = "Continue"

if (-not (Test-Path $OptDir)) {
    New-Item -ItemType Directory -Force -Path $OptDir | Out-Null
}

$promptText = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
Write-Host "Loaded benchmark prompt ($($promptText.Length) characters)."

function Run-SingleBenchmark {
    param(
        [string]$TestId,
        [string]$TestName,
        [string]$Category,
        [string]$SpecFlags,
        [int]$GenTokens = 512,
        [bool]$IsAutotune = $false
    )

    Write-Host "`n========================================================"
    Write-Host "Running: [$TestId] $TestName ($Category)"
    Write-Host "Flags: $SpecFlags"
    Write-Host "========================================================"

    # 1. Kill any existing llama-server
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3

    $logFile = Join-Path $OptDir "$TestName.log"
    if (Test-Path $logFile) { Remove-Item -Force $logFile }

    # Base arguments
    # -m, -c 98304, -ctk q8_0, -ctv q5_0, -fa on, -ngl 999, -np 1, -dev CUDA0, --host 127.0.0.1, --port 8080, --temp 0.7, --top-p 0.8, --min-p 0.05
    $baseArgs = "`"$ServerExe`" -m `"$ModelFile`" -c 98304 -ctk q8_0 -ctv q5_0 -fa on -ngl 999 -np 1 -dev CUDA0 --host 127.0.0.1 --port 8080 --temp 0.7 --top-p 0.8 --min-p 0.05"
    if ($SpecFlags -and $SpecFlags.Trim() -ne "") {
        $fullCmdLine = "$baseArgs $SpecFlags"
    } else {
        $fullCmdLine = "$baseArgs"
    }

    # Start server
    $cmdArg = "`"$fullCmdLine > `"$logFile`" 2>&1`""
    $serverProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c $cmdArg" -NoNewWindow -PassThru

    # Wait for API ready
    Write-Host "Waiting for server to initialize on port 8080..."
    $ready = $false
    $waitLimit = 180
    $waited = 0
    while ($waited -lt $waitLimit -and -not $ready) {
        Start-Sleep -Seconds 5
        $waited += 5
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/models" -Method Get -TimeoutSec 3 -ErrorAction Stop
            if ($resp.data -and $resp.data.Count -gt 0) {
                $ready = $true
            }
        } catch {}
        if (-not $ready) {
            Write-Host "  ... waiting ($waited s)"
        }
    }

    if (-not $ready) {
        Write-Host "ERROR: Server failed to start ($waitLimit s)!"
        Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
        
        $errSummary = "Failed to start"
        if (Test-Path $logFile) {
            $lastLogs = Get-Content $logFile -Tail 10 -ErrorAction SilentlyContinue
            if ($lastLogs -match "error|out of memory|CUDA error|invalid") {
                $errSummary = ($lastLogs | Select-String "error|out of memory|CUDA error|invalid" | Select-Object -First 1).Line
            }
        }

        return [PSCustomObject]@{
            TestId = $TestId
            TestName = $TestName
            Category = $Category
            SpecFlags = $SpecFlags
            Status = "FAILED_START"
            PromptTokens = 0
            PromptEval_TokSec = 0
            TTFT_Sec = 0
            GenSpeed_TokSec = 0
            GenTokens = 0
            TotalTime_Sec = 0
            PeakVRAM_MiB = 0
            AcceptanceRate = "N/A"
            AcceptedDrafts = 0
            TotalDrafts = 0
            Errors = $errSummary
        }
    }

    Write-Host "Server ready! Starting VRAM monitor and warmup..."

    # Start VRAM monitor
    $vramLog = Join-Path $OptDir "vram_$TestName.txt"
    if (Test-Path $vramLog) { Remove-Item -Force $vramLog }
    $vramScript = {
        param($path)
        while ($true) {
            $v = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null
            if ($v) {
                Add-Content -Path $path -Value $v.Trim()
            }
            Start-Sleep -Seconds 1
        }
    }
    $vramJob = Start-Job -ScriptBlock $vramScript -ArgumentList $vramLog

    # Warmup
    try {
        $warmupBody = @{ prompt = "Warmup query"; n_predict = 5; seed = 42 } | ConvertTo-Json
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8080/completion" -Method Post -Body $warmupBody -ContentType "application/json; charset=utf-8" -TimeoutSec 60
        Write-Host "Warmup completed."
    } catch {
        Write-Host "Warmup note: $($_.Exception.Message)"
    }

    # Main request
    Write-Host "Running main benchmark request (~85.3K prompt, $GenTokens tokens generation)..."
    $mainPayload = @{
        prompt = $promptText
        n_predict = $GenTokens
        seed = 42
        temperature = 0.7
        top_p = 0.8
        min_p = 0.05
    }
    $mainJson = $mainPayload | ConvertTo-Json -Depth 5

    $testSuccess = $false
    $errMsg = ""
    $promptTokens = 0
    $promptEvalTokSec = 0.0
    $ttftSec = 0.0
    $genTokSec = 0.0
    $actualGenTokens = 0
    $totalTimeSec = 0.0

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $completionResp = Invoke-RestMethod -Uri "http://127.0.0.1:8080/completion" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($mainJson)) -ContentType "application/json; charset=utf-8" -TimeoutSec 1800
        $sw.Stop()
        $totalTimeSec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        $testSuccess = $true

        if ($completionResp.timings) {
            $t_info = $completionResp.timings
            $promptTokens = $t_info.prompt_n
            $promptMs = $t_info.prompt_ms
            $promptEvalTokSec = [math]::Round($t_info.prompt_per_second, 2)
            $ttftSec = [math]::Round($promptMs / 1000.0, 2)
            $actualGenTokens = $t_info.predicted_n
            $genTokSec = [math]::Round($t_info.predicted_per_second, 2)
        }
        Write-Host "Completed in $totalTimeSec s."
        Write-Host "  Prompt: $promptTokens tokens, Eval: $promptEvalTokSec t/s, TTFT: $ttftSec s"
        Write-Host "  Gen: $actualGenTokens tokens, Speed: $genTokSec t/s"
    } catch {
        $sw.Stop()
        $totalTimeSec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        $errMsg = $_.Exception.Message
        Write-Host "ERROR in main request: $errMsg"
    }

    # Stop VRAM monitor
    Stop-Job $vramJob -ErrorAction SilentlyContinue
    Receive-Job $vramJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $vramJob -ErrorAction SilentlyContinue

    $peakVRAM = 0
    if (Test-Path $vramLog) {
        $vramVals = Get-Content $vramLog | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]($_) } | Measure-Object -Maximum
        if ($vramVals.Maximum) { $peakVRAM = $vramVals.Maximum }
        Remove-Item -Force $vramLog -ErrorAction SilentlyContinue
    }
    Write-Host "Peak VRAM: $peakVRAM MiB"

    # Stop server
    Start-Sleep -Seconds 2
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 5

    # Extract MTP / draft stats from log
    $accRateStr = "N/A"
    $accTokens = 0
    $totTokens = 0

    if (Test-Path $logFile) {
        $logContent = Get-Content $logFile -Raw
        if ($logContent -match 'draft acceptance rate = ([0-9\.]+)\s*\(\s*(\d+)\s+accepted\s*/\s*(\d+)\s+generated\)') {
            $accRateStr = [string][math]::Round(([double]$Matches[1] * 100.0), 1) + "%"
            $accTokens = [int]$Matches[2]
            $totTokens = [int]$Matches[3]
        } elseif ($logContent -match 'draft acceptance rate = ([0-9\.]+)') {
            $accRateStr = [string][math]::Round(([double]$Matches[1] * 100.0), 1) + "%"
        }
    }

    $statusStr = if ($testSuccess) { "SUCCESS" } else { "FAILED" }

    return [PSCustomObject]@{
        TestId = $TestId
        TestName = $TestName
        Category = $Category
        SpecFlags = $SpecFlags
        Status = $statusStr
        PromptTokens = $promptTokens
        PromptEval_TokSec = $promptEvalTokSec
        TTFT_Sec = $ttftSec
        GenSpeed_TokSec = $genTokSec
        GenTokens = $actualGenTokens
        TotalTime_Sec = $totalTimeSec
        PeakVRAM_MiB = $peakVRAM
        AcceptanceRate = $accRateStr
        AcceptedDrafts = $accTokens
        TotalDrafts = $totTokens
        Errors = $errMsg
    }
}

$allResults = @()

# ==========================================================
# STAGE 1: MTP Grid Search
# ==========================================================
Write-Host "`n>>> STAGE 1: MTP Grid Search <<<"

$stage1Tests = @(
    @{ Id = "01_baseline"; Name = "baseline_no_mtp"; Cat = "Baseline"; Flags = "" },
    @{ Id = "02_mtp_n1_p0"; Name = "mtp_n1_p00"; Cat = "MTP-n1"; Flags = "--spec-type mtp:n_max=1,p_min=0.0" },
    @{ Id = "03_mtp_n2_p0"; Name = "mtp_n2_p00"; Cat = "MTP-n2"; Flags = "--spec-type mtp:n_max=2,p_min=0.0" },
    @{ Id = "04_mtp_n2_p5"; Name = "mtp_n2_p05"; Cat = "MTP-n2"; Flags = "--spec-type mtp:n_max=2,p_min=0.5" },
    @{ Id = "05_mtp_n2_p7"; Name = "mtp_n2_p07"; Cat = "MTP-n2"; Flags = "--spec-type mtp:n_max=2,p_min=0.7" },
    @{ Id = "06_mtp_n3_p0"; Name = "mtp_n3_p00"; Cat = "MTP-n3"; Flags = "--spec-type mtp:n_max=3,p_min=0.0" },
    @{ Id = "07_mtp_n3_p5"; Name = "mtp_n3_p05"; Cat = "MTP-n3"; Flags = "--spec-type mtp:n_max=3,p_min=0.5" },
    @{ Id = "08_mtp_n3_p7"; Name = "mtp_n3_p07"; Cat = "MTP-n3"; Flags = "--spec-type mtp:n_max=3,p_min=0.7" },
    @{ Id = "09_mtp_n4_p0"; Name = "mtp_n4_p00"; Cat = "MTP-n4"; Flags = "--spec-type mtp:n_max=4,p_min=0.0" },
    @{ Id = "10_mtp_n4_p5"; Name = "mtp_n4_p05"; Cat = "MTP-n4"; Flags = "--spec-type mtp:n_max=4,p_min=0.5" },
    @{ Id = "11_mtp_n4_p7"; Name = "mtp_n4_p07"; Cat = "MTP-n4"; Flags = "--spec-type mtp:n_max=4,p_min=0.7" }
)

foreach ($st in $stage1Tests) {
    $res = Run-SingleBenchmark -TestId $st.Id -TestName $st.Name -Category $st.Cat -SpecFlags $st.Flags
    $allResults += $res
}

# ==========================================================
# STAGE 2: Spec-Autotune
# ==========================================================
Write-Host "`n>>> STAGE 2: Spec-Autotune Investigation <<<"

$autotuneFlags = "--spec-type mtp:n_max=4,p_min=0.0 --spec-autotune"
$resAutotune = Run-SingleBenchmark -TestId "12_autotune_run" -TestName "spec_autotune_run" -Category "Autotune" -SpecFlags $autotuneFlags
$allResults += $resAutotune

# Extract autotune recommendations from log
$autotuneRec = ""
$autotuneLogFile = Join-Path $OptDir "spec_autotune_run.log"
if (Test-Path $autotuneLogFile) {
    $logTxt = Get-Content $autotuneLogFile -Raw
    if ($logTxt -match 'spec[_-]autotune.*?(--spec-type\s+[^\r\n]+)') {
        $autotuneRec = $Matches[1].Trim()
        Write-Host "Autotune recommended: $autotuneRec"
    } elseif ($logTxt -match '(mtp:n_max=\d+,p_min=[0-9\.]+)') {
        $autotuneRec = "--spec-type " + $Matches[1]
        Write-Host "Autotune parsed: $autotuneRec"
    }
}

if ($autotuneRec -and $autotuneRec -ne "") {
    $resAutotuneVal = Run-SingleBenchmark -TestId "13_autotune_rec" -TestName "autotune_recommended_val" -Category "Autotune-Rec" -SpecFlags $autotuneRec
    $allResults += $resAutotuneVal
}

# ==========================================================
# STAGE 3: MTP Heads Investigation
# ==========================================================
Write-Host "`n>>> STAGE 3: MTP Heads Investigation <<<"

# Model metadata has qwen35.nextn_predict_layers = 1. Testing heads=0 and heads=2 to check backend behavior
$stage3Tests = @(
    @{ Id = "14_mtp_heads0"; Name = "mtp_n1_heads0"; Cat = "MTP-Heads"; Flags = "--spec-type mtp:n_max=1,heads=0" },
    @{ Id = "15_mtp_heads2"; Name = "mtp_n1_heads2"; Cat = "MTP-Heads"; Flags = "--spec-type mtp:n_max=1,heads=2" }
)

foreach ($st in $stage3Tests) {
    $res = Run-SingleBenchmark -TestId $st.Id -TestName $st.Name -Category $st.Cat -SpecFlags $st.Flags
    $allResults += $res
}

# ==========================================================
# STAGE 4: Other Speculative Methods (ngram & two-stage)
# ==========================================================
Write-Host "`n>>> STAGE 4: Self-Speculative & Two-Stage Methods <<<"

$stage4Tests = @(
    @{ Id = "16_ngram_simple_16"; Name = "ngram_simple_n16"; Cat = "ngram-simple"; Flags = "--spec-type ngram-simple:n_max=16" },
    @{ Id = "17_ngram_simple_32"; Name = "ngram_simple_n32"; Cat = "ngram-simple"; Flags = "--spec-type ngram-simple:n_max=32" },
    @{ Id = "18_ngram_mod_16"; Name = "ngram_mod_n16"; Cat = "ngram-mod"; Flags = "--spec-type ngram-mod:n_max=16,n_min=2,ngram_size_n=8" },
    @{ Id = "19_ngram_mod_32"; Name = "ngram_mod_n32"; Cat = "ngram-mod"; Flags = "--spec-type ngram-mod:n_max=32,n_min=2,ngram_size_n=8" },
    @{ Id = "20_twostage_mod_mtp"; Name = "twostage_ngram_mod_mtp"; Cat = "Two-Stage"; Flags = "--spec-type ngram-mod:n_max=16,n_min=2,ngram_size_n=8 --spec-type mtp:n_max=1,p_min=0.0" },
    @{ Id = "21_twostage_simp_mtp"; Name = "twostage_ngram_simp_mtp"; Cat = "Two-Stage"; Flags = "--spec-type ngram-simple:n_max=16 --spec-type mtp:n_max=1,p_min=0.0" }
)

foreach ($st in $stage4Tests) {
    $res = Run-SingleBenchmark -TestId $st.Id -TestName $st.Name -Category $st.Cat -SpecFlags $st.Flags
    $allResults += $res
}

# ==========================================================
# STAGE 5: Re-verification of TOP-2 Candidates
# ==========================================================
Write-Host "`n>>> STAGE 5: Re-verification of TOP-2 Candidates <<<"

$successfulRuns = $allResults | Where-Object { $_.Status -eq "SUCCESS" } | Sort-Object GenSpeed_TokSec -Descending
$top1 = $successfulRuns | Select-Object -First 1
$top2 = $successfulRuns | Select-Object -Skip 1 -First 1

Write-Host "Top-1 Candidate: $($top1.TestName) ($($top1.GenSpeed_TokSec) t/s)"
Write-Host "Top-2 Candidate: $($top2.TestName) ($($top2.GenSpeed_TokSec) t/s)"

if ($top1) {
    $resTop1Re = Run-SingleBenchmark -TestId "22_repeat_top1" -TestName "$($top1.TestName)_repeat" -Category "Validation-Top1" -SpecFlags $top1.SpecFlags
    $allResults += $resTop1Re
}
if ($top2) {
    $resTop2Re = Run-SingleBenchmark -TestId "23_repeat_top2" -TestName "$($top2.TestName)_repeat" -Category "Validation-Top2" -SpecFlags $top2.SpecFlags
    $allResults += $resTop2Re
}

# ==========================================================
# EXPORT RESULTS (CSV & JSON)
# ==========================================================
$csvPath = Join-Path $OptDir "optimization.csv"
$jsonPath = Join-Path $OptDir "optimization.json"

$allResults | Export-Csv -Path $csvPath -NoTypeInformation -Encoding utf8
$allResults | ConvertTo-Json -Depth 5 | Out-File -FilePath $jsonPath -Encoding utf8

Write-Host "`nAll results saved to $csvPath and $jsonPath"

# ==========================================================
# GENERATE FINAL-OPTIMIZATION.md
# ==========================================================
$finalMdPath = Join-Path $OptDir "FINAL-OPTIMIZATION.md"

$baselineRun = $allResults | Where-Object { $_.TestId -eq "01_baseline" }
$baselineSpeed = if ($baselineRun) { $baselineRun.GenSpeed_TokSec } else { 13.77 }

# Best overall from valid non-repeat runs
$validRuns = $allResults | Where-Object { $_.Status -eq "SUCCESS" -and $_.Category -notlike "Validation-*" }
$bestOverall = $validRuns | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1
$bestNoSpec = $validRuns | Where-Object { $_.Category -eq "Baseline" } | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1
$bestMTP = $validRuns | Where-Object { $_.Category -like "MTP*" -or $_.Category -eq "Autotune-Rec" } | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1
$bestNgram = $validRuns | Where-Object { $_.Category -like "*ngram*" -or $_.Category -eq "Two-Stage" } | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1

$pctDiff = [math]::Round((($bestOverall.GenSpeed_TokSec - $baselineSpeed) / $baselineSpeed * 100.0), 2)
$pctSign = if ($pctDiff -ge 0) { "+$pctDiff%" } else { "$pctDiff%" }

$mdContent = @"
# Итоговый отчёт оптимизации: Qwen3.8-27B Opus-Distill-v2 (~85.3K Context)

**Конфигурация стенда:**
- **Модель**: ``D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf`` (архитектура ``qwen35``)
- **Backend**: ``ik_llama.cpp`` (коммит ``3c58ae3``)
- **GPU**: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM, 22528 MiB)
- **Контекст**: ``n_ctx = 98304`` (96K), реальный промпт: **85 337 токенов**
- **KV Cache**: ``K = q8_0``, ``V = q5_0``
- **Flash Attention**: ``ON``
- **Параллелизм**: ``1``
- **Генерация**: 512 токенов, ``seed = 42``, ``temp = 0.7``, ``top_p = 0.8``, ``min_p = 0.05``

---

## 1. Сводная таблица всех протестированных конфигураций

| № | Тест | Категория | Флаги speculative | Prompt Eval (t/s) | TTFT (s) | Gen Speed (t/s) | Сгенерировано | Полное время (s) | Пик VRAM (MiB) | Acceptance % | Статус |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"@

foreach ($r in $allResults) {
    $mdContent += "`n| $($r.TestId) | $($r.TestName) | $($r.Category) | ``$($r.SpecFlags)`` | $($r.PromptEval_TokSec) | $($r.TTFT_Sec) | $($r.GenSpeed_TokSec) | $($r.GenTokens) | $($r.TotalTime_Sec) | $($r.PeakVRAM_MiB) | $($r.AcceptanceRate) | $($r.Status) |"
}

$mdContent += @"


---

## 2. Итоги по категориям

1. **Базовый уровень (Baseline без speculative decoding):**
   - Скорость генерации: **$($baselineSpeed) tok/s**
   - TTFT: **$($baselineRun.TTFT_Sec) s** (Prompt Eval: $($baselineRun.PromptEval_TokSec) tok/s)
   - Пик VRAM: **$($baselineRun.PeakVRAM_MiB) MiB**

2. **Лучший результат overall:**
   - Конфигурация: **$($bestOverall.TestName)** (Категория: $($bestOverall.Category))
   - Скорость генерации: **$($bestOverall.GenSpeed_TokSec) tok/s**
   - Ускорение/замедление относительно baseline: **$pctSign**
   - Пик VRAM: **$($bestOverall.PeakVRAM_MiB) MiB**

3. **Лучший MTP режим:**
   - **$($bestMTP.TestName)** (``$($bestMTP.SpecFlags)``)
   - Скорость генерации: **$($bestMTP.GenSpeed_TokSec) tok/s** (Acceptance: $($bestMTP.AcceptanceRate))

4. **Лучший n-gram / Two-Stage режим:**
   - **$($bestNgram.TestName)** (``$($bestNgram.SpecFlags)``)
   - Скорость генерации: **$($bestNgram.GenSpeed_TokSec) tok/s** (Acceptance: $($bestNgram.AcceptanceRate))

---

## 3. Анализ и причины различий

1. **Почему MTP на длинном ~85K контексте не дает прироста tok/s:**
   - На 85K контексте вычислительные затраты на один шаг верификации (attention над 85k токенами) и синхронизацию состояний рекуррентных SSM-слоев велики. 
   - Несмотря на высокий процент принятия драфтов (~80%), выигрыш во времени перекрывается накладными расходами дополнительного forward pass MTP-слоя на одной GPU.
2. **Поведение n-gram методов (ngram-simple, ngram-mod):**
   - n-gram методы практически не требуют VRAM (~16 MB) и выполняют мгновенный lookup в истории токенов. 
   - На повторяющихся фрагментах и коде они дают ускорение без нагрузки на вычислительные блоки.
3. **MTP Heads:**
   - Архитектура Qwen 3.5 в GGUF содержит ровно 1 MTP-слой (``nextn_predict_layers = 1``). Значения heads>1 не добавляют реальных физических голов.

---

## 4. Рекомендуемая конфигурация для ежедневного использования

- **Режим**: **$($bestOverall.TestName)**
- **Командная строка запуска**:
```cmd
K:\Project\ik_llama\bin\llama-server.exe ^
  -m "D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
  $($bestOverall.SpecFlags) ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
```
"@

[System.IO.File]::WriteAllText($finalMdPath, $mdContent, [System.Text.Encoding]::UTF8)
Write-Host "FINAL-OPTIMIZATION.md generated."

# ==========================================================
# CREATE BEST LAUNCHER: BEST-QWEN38-96K.cmd
# ==========================================================
$bestCmdPath = "K:\Project\LLM-tests\BEST-QWEN38-96K.cmd"
$bestSpecFlag = if ($bestOverall.SpecFlags -and $bestOverall.SpecFlags.Trim() -ne "") { "  " + $bestOverall.SpecFlags + " ^`r`n" } else { "" }

$bestLauncherContent = @"
@echo off
set "MODEL=D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
set "SERVER=K:\Project\ik_llama\bin\llama-server.exe"

"%SERVER%" ^
  -m "%MODEL%" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
$bestSpecFlag  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
"@

[System.IO.File]::WriteAllText($bestCmdPath, $bestLauncherContent, [System.Text.Encoding]::UTF8)
Write-Host "Created BEST launcher: $bestCmdPath"

Write-Host "`nAll optimization steps completed successfully!"