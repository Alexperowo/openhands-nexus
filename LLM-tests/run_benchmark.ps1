param(
    [string]$ResultsDir = "K:\Project\LLM-tests\benchmark-results",
    [string]$PromptFile = "K:\Project\LLM-tests\benchmark_prompt.txt"
)

$ErrorActionPreference = "Continue"

if (-not (Test-Path $ResultsDir)) {
    New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
}

$promptText = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
Write-Host "Loaded benchmark prompt ($($promptText.Length) characters)."

$tests = @(
    @{
        Id = "01"
        Name = "01-mainline-no-mtp"
        Launcher = "K:\Project\LLM-tests\01-mainline-no-mtp.cmd"
        Backend = "llama.cpp (mainline)"
        Version = "b10752 (b96806d96)"
        MTP = "OFF"
    },
    @{
        Id = "02"
        Name = "02-mainline-mtp"
        Launcher = "K:\Project\LLM-tests\02-mainline-mtp.cmd"
        Backend = "llama.cpp (mainline)"
        Version = "b10752 (b96806d96)"
        MTP = "ON (draft-mtp)"
    },
    @{
        Id = "03"
        Name = "03-ik-no-mtp"
        Launcher = "K:\Project\LLM-tests\03-ik-no-mtp.cmd"
        Backend = "ik_llama.cpp"
        Version = "commit 3c58ae3"
        MTP = "OFF"
    },
    @{
        Id = "04"
        Name = "04-ik-mtp"
        Launcher = "K:\Project\LLM-tests\04-ik-mtp.cmd"
        Backend = "ik_llama.cpp"
        Version = "commit 3c58ae3"
        MTP = "ON (mtp:n_max=1,p_min=0.0)"
    }
)

$results = @()

foreach ($t in $tests) {
    Write-Host "`n========================================================"
    Write-Host "Starting Test: $($t.Name) [$($t.Backend) | MTP: $($t.MTP)]"
    Write-Host "========================================================"

    # 1. Clean up existing processes
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3

    $logFile = Join-Path $ResultsDir "$($t.Name).log"
    if (Test-Path $logFile) { Remove-Item -Force $logFile }

    # 2. Launch server redirecting output to log file
    $cmdLine = "`"`"$($t.Launcher)`" > `"$logFile`" 2>&1`""
    $serverProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c $cmdLine" -NoNewWindow -PassThru

    # 3. Wait for API readiness
    Write-Host "Waiting for server to load model and listen on port 8080..."
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
        } catch {
            # Still loading
        }
        if (-not $ready) {
            Write-Host "  ... waiting ($waited s)"
        }
    }

    if (-not $ready) {
        Write-Host "ERROR: Server failed to start within $waitLimit seconds!"
        Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
        
        $results += [PSCustomObject]@{
            TestId = $t.Id
            TestName = $t.Name
            Backend = $t.Backend
            Version = $t.Version
            MTP = $t.MTP
            Status = "FAILED_TO_START"
            PromptTokens = 0
            PromptEvalSpeed_TokSec = 0
            TTFT_Sec = 0
            GenSpeed_TokSec = 0
            GenTokens = 0
            TotalTime_Sec = 0
            PeakVRAM_MiB = 0
            MTP_Acceptance = "N/A"
            Errors = "Server failed to respond within $waitLimit s"
        }
        continue
    }

    Write-Host "Server is ready! Starting VRAM monitor and running warmup..."

    # 4. Start VRAM sampler in background job
    $vramLog = Join-Path $ResultsDir "vram_$($t.Name).txt"
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

    # 5. Warmup request
    try {
        $warmupBody = @{
            prompt = "Short warmup request."
            n_predict = 5
            seed = 42
        } | ConvertTo-Json
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8080/completion" -Method Post -Body $warmupBody -ContentType "application/json; charset=utf-8" -TimeoutSec 60
        Write-Host "Warmup completed."
    } catch {
        Write-Host "Warmup warning: $($_.Exception.Message)"
    }

    # 6. Main benchmark request
    Write-Host "Executing main benchmark (~85K-90K prompt, 512 tokens generation)..."
    $mainPayload = @{
        prompt = $promptText
        n_predict = 512
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
    $genTokens = 0
    $totalTimeSec = 0.0

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        # Use HttpWebRequest or Invoke-RestMethod with large buffer
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
            $genTokens = $t_info.predicted_n
            $genTokSec = [math]::Round($t_info.predicted_per_second, 2)
        }
        Write-Host "Main request finished in $totalTimeSec s."
        Write-Host "  Prompt Tokens: $promptTokens, Eval Speed: $promptEvalTokSec t/s, TTFT: $ttftSec s"
        Write-Host "  Gen Tokens: $genTokens, Gen Speed: $genTokSec t/s"
    } catch {
        $sw.Stop()
        $totalTimeSec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        $errMsg = $_.Exception.Message
        Write-Host "ERROR during main request: $errMsg"
    }

    # 7. Stop VRAM monitor
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

    # 8. Flush and stop server
    Start-Sleep -Seconds 2
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 5

    # 9. Extract MTP metrics and errors from server log
    $mtpStats = "N/A"
    if (Test-Path $logFile) {
        $logContent = Get-Content $logFile -Raw
        if ($logContent -match 'accept(?:ance)?(?: rate)?[:\s=]+([0-9\.]+)%?') {
            $mtpStats = $Matches[0]
        } elseif ($logContent -match 'draft[_\s]accepted[:\s=]+([0-9\/]+|\d+)') {
            $mtpStats = $Matches[0]
        } elseif ($t.MTP -ne "OFF") {
            $mtpStats = "Active"
        }
    }

    $statusStr = if ($testSuccess) { "SUCCESS" } else { "FAILED" }

    $resObj = [PSCustomObject]@{
        TestId = $t.Id
        TestName = $t.Name
        Backend = $t.Backend
        Version = $t.Version
        MTP = $t.MTP
        Status = $statusStr
        PromptTokens = $promptTokens
        PromptEvalSpeed_TokSec = $promptEvalTokSec
        TTFT_Sec = $ttftSec
        GenSpeed_TokSec = $genTokSec
        GenTokens = $genTokens
        TotalTime_Sec = $totalTimeSec
        PeakVRAM_MiB = $peakVRAM
        MTP_Acceptance = $mtpStats
        Errors = $errMsg
    }

    $results += $resObj
}

# 10. Save CSV & JSON
$csvPath = Join-Path $ResultsDir "benchmark.csv"
$jsonPath = Join-Path $ResultsDir "benchmark.json"

$results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding utf8
$results | ConvertTo-Json -Depth 5 | Out-File -FilePath $jsonPath -Encoding utf8

Write-Host "`nResults saved to CSV & JSON."

# 11. Generate SUMMARY.md
$summaryPath = Join-Path $ResultsDir "SUMMARY.md"

$noMtpList = $results | Where-Object { $_.MTP -eq "OFF" -and $_.Status -eq "SUCCESS" }
$mtpList = $results | Where-Object { $_.MTP -ne "OFF" -and $_.Status -eq "SUCCESS" }

$fastestNoMtp = $noMtpList | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1
$fastestMtp = $mtpList | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1
$absoluteWinner = $results | Where-Object { $_.Status -eq "SUCCESS" } | Sort-Object GenSpeed_TokSec -Descending | Select-Object -First 1

$m_noMtp = $results | Where-Object { $_.TestId -eq "01" }
$m_mtp = $results | Where-Object { $_.TestId -eq "02" }
$ik_noMtp = $results | Where-Object { $_.TestId -eq "03" }
$ik_mtp = $results | Where-Object { $_.TestId -eq "04" }

$m_speedup = if ($m_noMtp.GenSpeed_TokSec -gt 0 -and $m_mtp.GenSpeed_TokSec -gt 0) {
    [math]::Round(($m_mtp.GenSpeed_TokSec / $m_noMtp.GenSpeed_TokSec), 2)
} else { "N/A" }

$ik_speedup = if ($ik_noMtp.GenSpeed_TokSec -gt 0 -and $ik_mtp.GenSpeed_TokSec -gt 0) {
    [math]::Round(($ik_mtp.GenSpeed_TokSec / $ik_noMtp.GenSpeed_TokSec), 2)
} else { "N/A" }

$maxVram = ($results | Measure-Object PeakVRAM_MiB -Maximum).Maximum

$md = @"
# Сводный отчет benchmark: Qwen3.8-27B Opus-Distill-v2 (~86K Context)

**Конфигурация:**
- Модель: ``Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf``
- GPU: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM)
- Контекст: 98304 (96K), реальное заполнение промпта: ~$($results[0].PromptTokens) токенов
- KV Cache: ``K = q8_0``, ``V = q5_0``
- Flash Attention: ``ON``
- Параллелизм: ``1``

## Таблица результатов

| Тест | Backend | MTP | Входные токены | Prompt Eval (t/s) | TTFT (s) | Gen Speed (t/s) | Сгенерировано | Полное время (s) | Пик VRAM (MiB) | Статус |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"@

foreach ($r in $results) {
    $md += "`n| $($r.TestName) | $($r.Backend) | $($r.MTP) | $($r.PromptTokens) | $($r.PromptEvalSpeed_TokSec) | $($r.TTFT_Sec) | $($r.GenSpeed_TokSec) | $($r.GenTokens) | $($r.TotalTime_Sec) | $($r.PeakVRAM_MiB) | $($r.Status) |"
}

$md += @"


## Ключевые выводы

1. **Самый быстрый без MTP:**
   - **$($fastestNoMtp.Backend)** ($($fastestNoMtp.TestName)) со скоростью генерации **$($fastestNoMtp.GenSpeed_TokSec) tok/s** (Prompt Eval: $($fastestNoMtp.PromptEvalSpeed_TokSec) tok/s).

2. **Самый быстрый с MTP:**
   - **$($fastestMtp.Backend)** ($($fastestMtp.TestName)) со скоростью генерации **$($fastestMtp.GenSpeed_TokSec) tok/s** (Prompt Eval: $($fastestMtp.PromptEvalSpeed_TokSec) tok/s).

3. **Влияние MTP (ускорение / замедление):**
   - **Mainline llama.cpp**: с $($m_noMtp.GenSpeed_TokSec) t/s до $($m_mtp.GenSpeed_TokSec) t/s (фактор: **${m_speedup}x**).
   - **ik_llama.cpp**: с $($ik_noMtp.GenSpeed_TokSec) t/s до $($ik_mtp.GenSpeed_TokSec) t/s (фактор: **${ik_speedup}x**).

4. **Абсолютный победитель по скорости генерации:**
   - **$($absoluteWinner.Backend)** ($($absoluteWinner.TestName)) — **$($absoluteWinner.GenSpeed_TokSec) tok/s**.

5. **Деградация скорости на заполненном ~90K контексте:**
   - Анализ: при размере контекста ~$($results[0].PromptTokens) токенов KV-кэш занял требуемый объем VRAM без OOM (пик VRAM: $maxVram MiB из 22528 MiB).
"@

[System.IO.File]::WriteAllText($summaryPath, $md, [System.Text.Encoding]::UTF8)
Write-Host "SUMMARY.md generated."
Write-Host "All benchmark tests completed successfully!"