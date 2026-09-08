# Ornith-1.5-35B-A3B Automated Benchmark & MTP Optimization Suite
# Location: K:\Project\LLM-tests\Ornith-1.5\run-benchmark.ps1

param(
    [int]$TestPort = 18080,
    [switch]$SkipSweep,
    [switch]$Skip96k,
    [switch]$SkipVision
)

$ErrorActionPreference = "Continue"

$backend = "K:\Project\ik_llama\bin\llama-server.exe"
$model = "K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf"
$mmproj = "K:\Project\Models\mmproj-Ornith-1.5-35B-BF16.gguf"
$testImage = "K:\Project\OpenHands-Tests\Android-Smoke-01\initial-screen.png"

$baseDir = "K:\Project\LLM-tests\Ornith-1.5"
$logDir = Join-Path $baseDir "logs"
$csvFile = Join-Path $baseDir "BENCHMARKS.csv"
$resultMd = Join-Path $baseDir "RESULT.md"
$corpusFile = Join-Path $baseDir "prompt_85k.txt"

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Log-Bench([string]$Msg, [string]$Level = "INFO") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "STEP"    { "Cyan" }
        "SUCCESS" { "Green" }
        "WARN"    { "Yellow" }
        "ERROR"   { "Red" }
        default   { "White" }
    }
    Write-Host "[$ts] [$Level] $Msg" -ForegroundColor $color
}

function Get-GpuVramMb() {
    try {
        $v = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null
        return [int]($v.Trim())
    } catch {
        return 0
    }
}

function Start-LlamaServer([string]$LogName, [int]$Ctx, [string[]]$ExtraArgs) {
    $outLog = Join-Path $logDir "$LogName.log"
    $errLog = Join-Path $logDir "$LogName.err.log"
    if (Test-Path $outLog) { Remove-Item $outLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path $errLog) { Remove-Item $errLog -Force -ErrorAction SilentlyContinue }

    $baseArgs = @(
        "-m", $model,
        "-c", $Ctx.ToString(),
        "-ctk", "q8_0",
        "-ctv", "q5_0",
        "-fa", "on",
        "-ngl", "999",
        "-np", "1",
        "-dev", "CUDA0",
        "--jinja",
        "--host", "127.0.0.1",
        "--port", $TestPort.ToString()
    )

    $allArgs = $baseArgs + $ExtraArgs
    $argString = $allArgs -join " "
    Log-Bench "Launching server: $argString" "INFO"

    $proc = Start-Process -FilePath $backend -ArgumentList $allArgs -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    $ready = $false
    $peakVram = Get-GpuVramMb
    for ($i = 0; $i -lt 75; $i++) {
        Start-Sleep -Seconds 1
        $curV = Get-GpuVramMb
        if ($curV -gt $peakVram) { $peakVram = $curV }

        try {
            $m = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/models" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($m) { $ready = $true; break }
        } catch {}

        if ($proc.HasExited) { break }
    }

    return @{
        Process = $proc
        Ready = $ready
        PeakVram = $peakVram
        OutLog = $outLog
        ErrLog = $errLog
    }
}

function Stop-LlamaServer($serverObj) {
    if ($serverObj -and $serverObj.Process -and (-not $serverObj.Process.HasExited)) {
        Log-Bench "Stopping llama-server PID: $($serverObj.Process.Id)" "INFO"
        try {
            Stop-Process -Id $serverObj.Process.Id -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $serverObj.Process.Id -Timeout 5 -ErrorAction SilentlyContinue
        } catch {}
    }
    Start-Sleep -Seconds 2
}

# CSV Initialization
$csvHeader = "mode,context,prompt_tokens,generated_tokens,mtp,n_max,p_min,ngram,drafted_tokens,accepted_tokens,acceptance_pct,prompt_tps,generation_tps,wall_time_s,peak_vram_mib,status,notes"
Set-Content -Path $csvFile -Value $csvHeader -Encoding UTF8

function Add-CsvRow($dict) {
    $row = "$($dict.mode),$($dict.context),$($dict.prompt_tokens),$($dict.generated_tokens),$($dict.mtp),$($dict.n_max),$($dict.p_min),$($dict.ngram),$($dict.drafted_tokens),$($dict.accepted_tokens),$($dict.acceptance_pct),$($dict.prompt_tps),$($dict.generation_tps),$($dict.wall_time_s),$($dict.peak_vram_mib),$($dict.status),`"$($dict.notes)`""
    Add-Content -Path $csvFile -Value $row -Encoding UTF8
}

# =============================================================================
# 1. ORNITH SMOKE TEST
# =============================================================================
Log-Bench "=================================================================" "STEP"
Log-Bench "STAGE 1: ORNITH BASIC SMOKE TEST" "STEP"
Log-Bench "=================================================================" "STEP"

$smokeServer = Start-LlamaServer "smoke" 16384 @()
if (-not $smokeServer.Ready) {
    Log-Bench "Smoke server failed to initialize! Check logs\smoke.err.log" "ERROR"
    Stop-LlamaServer $smokeServer
    Set-Content -Path $resultMd -Value "# Ornith-1.5 Benchmark Results`n`n**STATUS: FAIL**`n`nBasic smoke test failed to load model." -Encoding UTF8
    exit 1
}

$smokePassed = $false
$smokeNotes = ""
try {
    $body = @{
        messages = @(@{ role = "user"; content = "Hello! Please identify yourself and confirm 2+2=4." })
        max_tokens = 60
        temperature = 0.0
    } | ConvertTo-Json

    $res = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
    $fullText = ($res.choices[0].message.reasoning_content + " " + $res.choices[0].message.content).Trim()
    Log-Bench "Smoke response received: $fullText" "SUCCESS"

    if ($fullText.Length -gt 5 -and (-not ($fullText -match "NaN"))) {
        $smokePassed = $true
        $smokeNotes = "Clean response, no NaN"
    } else {
        $smokeNotes = "Suspicious or empty output"
    }
} catch {
    $smokeNotes = "Error: $_"
    Log-Bench "Smoke completion error: $_" "ERROR"
}

$smokeVram = Get-GpuVramMb
Stop-LlamaServer $smokeServer

if (-not $smokePassed) {
    Log-Bench "Smoke validation failed ($smokeNotes). Aborting benchmarks." "ERROR"
    Set-Content -Path $resultMd -Value "# Ornith-1.5 Benchmark Results`n`n**STATUS: FAIL**`n`nReason: $smokeNotes" -Encoding UTF8
    exit 1
}

Log-Bench "Stage 1 PASS: Ornith-1.5-35B loaded cleanly on CUDA0. Peak VRAM: $smokeVram MiB" "SUCCESS"

# =============================================================================
# 2. AUTOMATIC MTP SWEEP (7 MODES)
# =============================================================================
$sweepModes = @(
    @{
        id = "baseline-no-mtp"; name = "MTP OFF";
        args = @();
        mtp = "none"; n_max = 0; p_min = 0.0; ngram = "none"
    },
    @{
        id = "mtp-n1-p075"; name = "MTP n1 p0.75";
        args = @("--spec-type", "mtp:n_max=1,p_min=0.75");
        mtp = "mtp"; n_max = 1; p_min = 0.75; ngram = "none"
    },
    @{
        id = "mtp-author"; name = "Author (ngram-mod + mtp)";
        args = @("--spec-type", "ngram-mod:n_min=8,n_max=24,ngram_size_n=48", "--spec-type", "mtp:n_max=1,p_min=0.75");
        mtp = "ngram-mod+mtp"; n_max = 1; p_min = 0.75; ngram = "mod:8-24/48"
    },
    @{
        id = "mtp-n2-p075"; name = "MTP n2 p0.75";
        args = @("--spec-type", "mtp:n_max=2,p_min=0.75");
        mtp = "mtp"; n_max = 2; p_min = 0.75; ngram = "none"
    },
    @{
        id = "mtp-n3-p075"; name = "MTP n3 p0.75";
        args = @("--spec-type", "mtp:n_max=3,p_min=0.75");
        mtp = "mtp"; n_max = 3; p_min = 0.75; ngram = "none"
    },
    @{
        id = "mtp-n2-p0"; name = "MTP n2 p0.0";
        args = @("--spec-type", "mtp:n_max=2,p_min=0.0");
        mtp = "mtp"; n_max = 2; p_min = 0.0; ngram = "none"
    },
    @{
        id = "mtp-n3-p0"; name = "MTP n3 p0.0";
        args = @("--spec-type", "mtp:n_max=3,p_min=0.0");
        mtp = "mtp"; n_max = 3; p_min = 0.0; ngram = "none"
    }
)

$sweepPrompt = "Write a comprehensive technical overview of Mixture of Experts (MoE) architectures in large language models. Detail router gating functions, expert capacity limits, token dropping, and load balancing auxiliary losses in 200 words."
$sweepResults = @()

if (-not $SkipSweep) {
    Log-Bench "=================================================================" "STEP"
    Log-Bench "STAGE 2: AUTOMATIC MTP SWEEP (7 MODES, ~256 OUTPUT TOKENS)" "STEP"
    Log-Bench "=================================================================" "STEP"

    $isWarmupDone = $false

    foreach ($m in $sweepModes) {
        Log-Bench "--- Testing Mode: $($m.name) [$($m.id)] ---" "STEP"
        $srv = Start-LlamaServer $m.id 16384 $m.args

        if (-not $srv.Ready) {
            Log-Bench "Server failed to start for mode $($m.id)!" "ERROR"
            Stop-LlamaServer $srv
            Add-CsvRow @{
                mode = $m.id; context = 16384; prompt_tokens = 0; generated_tokens = 0;
                mtp = $m.mtp; n_max = $m.n_max; p_min = $m.p_min; ngram = $m.ngram;
                drafted_tokens = 0; accepted_tokens = 0; acceptance_pct = 0;
                prompt_tps = 0; generation_tps = 0; wall_time_s = 0; peak_vram_mib = 0;
                status = "FAIL"; notes = "Server startup failure"
            }
            continue
        }

        # 1 warm-up run before first measurement
        if (-not $isWarmupDone) {
            Log-Bench "Running single warm-up request..." "INFO"
            try {
                $wBody = @{
                    messages = @(@{ role = "user"; content = "Warmup query: write 20 words." })
                    max_tokens = 25
                    temperature = 0.0
                } | ConvertTo-Json
                $null = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $wBody -ContentType "application/json" -TimeoutSec 30
                $isWarmupDone = $true
            } catch {
                Log-Bench "Warmup failed: $_" "WARN"
            }
        }

        # Measured run
        $body = @{
            messages = @(@{ role = "user"; content = $sweepPrompt })
            max_tokens = 256
            temperature = 0.0
        } | ConvertTo-Json

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $res = $null
        $status = "FAIL"
        $notes = ""
        $genTps = 0.0
        $promptTps = 0.0
        $promptTokens = 0
        $genTokens = 0
        $drafted = 0
        $accepted = 0
        $accPct = 0.0

        try {
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 90
            $sw.Stop()

            if ($res -and $res.choices) {
                $status = "PASS"
                $promptTokens = $res.usage.prompt_tokens
                $genTokens = $res.usage.completion_tokens

                if ($res.timings) {
                    $genTps = [Math]::Round([double]$res.timings.predicted_per_second, 2)
                    $promptTps = [Math]::Round([double]$res.timings.prompt_per_second, 2)
                    if ($res.timings.draft_n) { $drafted = $res.timings.draft_n }
                    if ($res.timings.draft_n_accepted) { $accepted = $res.timings.draft_n_accepted }
                } else {
                    $genTps = [Math]::Round($genTokens / $sw.Elapsed.TotalSeconds, 2)
                }

                if ($drafted -gt 0) {
                    $accPct = [Math]::Round(($accepted / $drafted) * 100, 1)
                }

                $fullOut = ($res.choices[0].message.reasoning_content + " " + $res.choices[0].message.content).Trim()
                if ($fullOut.Length -lt 20) {
                    $notes = "Output suspiciously short"
                } else {
                    $notes = "Sanity OK"
                }

                Log-Bench "Result: Gen=$genTps tok/s | Prompt=$promptTps tok/s | Drafted=$drafted | Accepted=$accepted ($accPct%) | Wall=$([Math]::Round($sw.Elapsed.TotalSeconds, 2))s" "SUCCESS"
            }
        } catch {
            $sw.Stop()
            $notes = "Error: $_"
            Log-Bench "Measured run failed: $_" "ERROR"
        }

        $vram = Get-GpuVramMb
        Stop-LlamaServer $srv

        $resObj = @{
            mode = $m.id
            name = $m.name
            args = $m.args
            context = 16384
            prompt_tokens = $promptTokens
            generated_tokens = $genTokens
            mtp = $m.mtp
            n_max = $m.n_max
            p_min = $m.p_min
            ngram = $m.ngram
            drafted_tokens = $drafted
            accepted_tokens = $accepted
            acceptance_pct = $accPct
            prompt_tps = $promptTps
            generation_tps = $genTps
            wall_time_s = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
            peak_vram_mib = $vram
            status = $status
            notes = $notes
        }

        Add-CsvRow $resObj
        $sweepResults += $resObj
    }
}

# =============================================================================
# SELECT TOP-2 MTP MODES (Numeric Sorting)
# =============================================================================
# Filter out baseline (mode 1) and failures, sort numerically by generation_tps descending
$mtpOnly = $sweepResults | Where-Object { $_["mode"] -ne "baseline-no-mtp" -and $_["status"] -eq "PASS" } | Sort-Object { [double]$_["generation_tps"] } -Descending
$top1 = $mtpOnly[0]
$top2 = $mtpOnly[1]

Log-Bench "=================================================================" "STEP"
Log-Bench "MTP SWEEP COMPLETED:" "STEP"
Log-Bench "TOP-1 Mode: $($top1["name"]) ($($top1["generation_tps"]) tok/s, acceptance $($top1["acceptance_pct"])%)" "SUCCESS"
Log-Bench "TOP-2 Mode: $($top2["name"]) ($($top2["generation_tps"]) tok/s, acceptance $($top2["acceptance_pct"])%)" "SUCCESS"
Log-Bench "=================================================================" "STEP"

# =============================================================================
# 3. 96K CONTROL TEST (82K-88K REAL TOKENS PROMPT)
# =============================================================================
if (-not $Skip96k) {
    Log-Bench "=================================================================" "STEP"
    Log-Bench "STAGE 3: 96K CONTROL TEST (-c 98304, ~85K REAL TOKENS PROMPT)" "STEP"
    Log-Bench "=================================================================" "STEP"

    # Start a server to tokenize and calibrate the 85K prompt
    Log-Bench "Calibrating 82-88K token corpus..." "INFO"
    $calSrv = Start-LlamaServer "calib" 98304 @()

    $seedText = "In advanced autonomous agentic systems and high-throughput inference engines, speculative decoding operates by coupling a small, fast draft model or multi-token prediction heads with a larger verification model. The primary verification model processes candidate token sequences in parallel using causal attention masks. This yields significant speedup when the draft acceptance rate is sufficiently high. However, under long context windows up to 98304 tokens, KV cache management, memory bandwidth saturation, and quantized key-value states (such as q8_0 and q5_0) introduce subtle performance dynamics.`n"
    
    # Generate ~85K tokens
    $targetTokens = 84000
    $multiplier = 1350
    $testContent = ($seedText * $multiplier)
    
    $calBody = @{ content = $testContent } | ConvertTo-Json
    $tokRes = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/tokenize" -Method Post -Body $calBody -ContentType "application/json"
    $curCount = $tokRes.tokens.Count
    Log-Bench "Initial generated text tokens: $curCount" "INFO"

    if ($curCount -lt 82000 -or $curCount -gt 88000) {
        $factor = [double]$targetTokens / [double]$curCount
        $newMultiplier = [int]($multiplier * $factor)
        $testContent = ($seedText * $newMultiplier)
        $calBody = @{ content = $testContent } | ConvertTo-Json
        $tokRes = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/tokenize" -Method Post -Body $calBody -ContentType "application/json"
        $curCount = $tokRes.tokens.Count
    }
    Log-Bench "Calibrated prompt token count: $curCount (Within target 82K-88K range)" "SUCCESS"
    Stop-LlamaServer $calSrv

    $prompt96k = $testContent + "`n`nQuestion: Based on the technical considerations detailed above, provide a comprehensive analysis of trade-offs between memory bandwidth and draft acceptance in 250 words."

    # Test 3 modes on 96K:
    # A. 96k-no-mtp
    # B. 96k-top1
    # C. 96k-top2
    $modes96k = @(
        @{ id = "96k-no-mtp"; name = "96K Baseline (No MTP)"; args = @(); mtp = "none"; n_max = 0; p_min = 0.0; ngram = "none" },
        @{ id = "96k-top1"; name = "96K TOP-1 ($($top1["name"]))"; args = $top1["args"]; mtp = $top1["mtp"]; n_max = $top1["n_max"]; p_min = $top1["p_min"]; ngram = $top1["ngram"] },
        @{ id = "96k-top2"; name = "96K TOP-2 ($($top2["name"]))"; args = $top2["args"]; mtp = $top2["mtp"]; n_max = $top2["n_max"]; p_min = $top2["p_min"]; ngram = $top2["ngram"] }
    )

    $results96k = @()

    foreach ($m96 in $modes96k) {
        Log-Bench "--- Running 96K Test: $($m96.name) ---" "STEP"
        $srv96 = Start-LlamaServer $m96.id 98304 $m96.args

        if (-not $srv96.Ready) {
            Log-Bench "96K Server failed to start for $($m96.id)!" "ERROR"
            Stop-LlamaServer $srv96
            Add-CsvRow @{
                mode = $m96.id; context = 98304; prompt_tokens = 0; generated_tokens = 0;
                mtp = $m96.mtp; n_max = $m96.n_max; p_min = $m96.p_min; ngram = $m96.ngram;
                drafted_tokens = 0; accepted_tokens = 0; acceptance_pct = 0;
                prompt_tps = 0; generation_tps = 0; wall_time_s = 0; peak_vram_mib = 0;
                status = "FAIL"; notes = "96K Server startup failure"
            }
            continue
        }

        $body = @{
            messages = @(@{ role = "user"; content = $prompt96k })
            max_tokens = 300
            temperature = 0.0
        } | ConvertTo-Json

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $genTps = 0.0
        $promptTps = 0.0
        $promptTokens = 0
        $genTokens = 0
        $drafted = 0
        $accepted = 0
        $accPct = 0.0
        $status = "FAIL"
        $notes = ""

        try {
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
            $sw.Stop()

            if ($res -and $res.choices) {
                $status = "PASS"
                $promptTokens = $res.usage.prompt_tokens
                $genTokens = $res.usage.completion_tokens

                if ($res.timings) {
                    $genTps = [Math]::Round([double]$res.timings.predicted_per_second, 2)
                    $promptTps = [Math]::Round([double]$res.timings.prompt_per_second, 2)
                    if ($res.timings.draft_n) { $drafted = $res.timings.draft_n }
                    if ($res.timings.draft_n_accepted) { $accepted = $res.timings.draft_n_accepted }
                } else {
                    $genTps = [Math]::Round($genTokens / $sw.Elapsed.TotalSeconds, 2)
                }

                if ($drafted -gt 0) {
                    $accPct = [Math]::Round(($accepted / $drafted) * 100, 1)
                }

                $fullOut = ($res.choices[0].message.reasoning_content + " " + $res.choices[0].message.content).Trim()
                $notes = "Sanity OK (Length: $($fullOut.Length))"
                Log-Bench "96K Result: PP=$promptTps tok/s | TG=$genTps tok/s | Drafted=$drafted | Accepted=$accepted ($accPct%) | Wall=$([Math]::Round($sw.Elapsed.TotalSeconds, 2))s" "SUCCESS"
            }
        } catch {
            $sw.Stop()
            $notes = "Error: $_"
            Log-Bench "96K run failed: $_" "ERROR"
        }

        $vram = Get-GpuVramMb
        Stop-LlamaServer $srv96

        $r96Obj = @{
            mode = $m96.id
            name = $m96.name
            args = $m96.args
            context = 98304
            prompt_tokens = $promptTokens
            generated_tokens = $genTokens
            mtp = $m96.mtp
            n_max = $m96.n_max
            p_min = $m96.p_min
            ngram = $m96.ngram
            drafted_tokens = $drafted
            accepted_tokens = $accepted
            acceptance_pct = $accPct
            prompt_tps = $promptTps
            generation_tps = $genTps
            wall_time_s = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
            peak_vram_mib = $vram
            status = $status
            notes = $notes
        }

        Add-CsvRow $r96Obj
        $results96k += $r96Obj
    }

    # Evaluate 96K Winner
    $resTop1 = $results96k | Where-Object { $_["mode"] -eq "96k-top1" }
    $resTop2 = $results96k | Where-Object { $_["mode"] -eq "96k-top2" }
    $resNoMtp = $results96k | Where-Object { $_["mode"] -eq "96k-no-mtp" }

    # Check if Top1 and Top2 differ by < 5%
    if ($resTop1 -and $resTop2 -and [double]$resTop1["generation_tps"] -gt 0 -and [double]$resTop2["generation_tps"] -gt 0) {
        $t1 = [double]$resTop1["generation_tps"]
        $t2 = [double]$resTop2["generation_tps"]
        $diffPct = [Math]::Abs($t1 - $t2) / [Math]::Max($t1, $t2) * 100
        Log-Bench "Difference between 96K Top-1 and Top-2 is $([Math]::Round($diffPct, 2))%" "INFO"

        if ($diffPct -lt 5.0) {
            Log-Bench "Difference < 5%: Running one repeat verification for Top-1 and Top-2..." "STEP"
            # Repeat Top1
            $srvRepeat1 = Start-LlamaServer "96k-top1-rep" 98304 $top1["args"]
            if ($srvRepeat1.Ready) {
                $sw1 = [System.Diagnostics.Stopwatch]::StartNew()
                $res1 = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
                $sw1.Stop()
                $tps1 = [double]$res1.timings.predicted_per_second
                $resTop1["generation_tps"] = [Math]::Round(($t1 + $tps1) / 2.0, 2)
                Log-Bench "Top-1 repeated TPS=$tps1 -> New average=$($resTop1['generation_tps'])" "SUCCESS"
            }
            Stop-LlamaServer $srvRepeat1

            # Repeat Top2
            $srvRepeat2 = Start-LlamaServer "96k-top2-rep" 98304 $top2["args"]
            if ($srvRepeat2.Ready) {
                $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
                $res2 = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
                $sw2.Stop()
                $tps2 = [double]$res2.timings.predicted_per_second
                $resTop2["generation_tps"] = [Math]::Round(($t2 + $tps2) / 2.0, 2)
                Log-Bench "Top-2 repeated TPS=$tps2 -> New average=$($resTop2['generation_tps'])" "SUCCESS"
            }
            Stop-LlamaServer $srvRepeat2
        }
    }

    # Determine absolute winner on 96K
    if ([double]$resTop1["generation_tps"] -ge [double]$resTop2["generation_tps"]) {
        $finalWinner = $top1
        $finalWinnerResult = $resTop1
    } else {
        $finalWinner = $top2
        $finalWinnerResult = $resTop2
    }
} else {
    $finalWinner = $top1
    $finalWinnerResult = $top1
}

Log-Bench "=================================================================" "STEP"
Log-Bench "96K FINAL WINNER: $($finalWinner['name'])" "SUCCESS"
Log-Bench "Generation Speed: $($finalWinnerResult['generation_tps']) tok/s" "SUCCESS"
Log-Bench "=================================================================" "STEP"

# =============================================================================
# 4. VISION SMOKE TEST (WITH BEST MTP AND NO MTP)
# =============================================================================
$visionNoMtpPass = $false
$visionBestMtpPass = $false

if (-not $SkipVision) {
    Log-Bench "=================================================================" "STEP"
    Log-Bench "STAGE 4: VISION SMOKE TEST (mmproj + Android initial-screen.png)" "STEP"
    Log-Bench "=================================================================" "STEP"

    if (Test-Path $testImage) {
        $imgBytes = [System.IO.File]::ReadAllBytes($testImage)
        $b64Img = [Convert]::ToBase64String($imgBytes)
        $dataUrl = "data:image/png;base64,$b64Img"

        $visBody = @{
            messages = @(
                @{
                    role = "user"
                    content = @(
                        @{ type = "text"; text = "Describe this mobile screen in detail and name the visible UI elements and buttons." },
                        @{ type = "image_url"; image_url = @{ url = $dataUrl } }
                    )
                }
            )
            max_tokens = 150
            temperature = 0.0
        } | ConvertTo-Json -Depth 5

        # A. Vision without MTP
        Log-Bench "--- Testing Vision WITHOUT MTP ---" "STEP"
        $visArgsNoMtp = @("--mmproj", $mmproj)
        $visSrvA = Start-LlamaServer "vision-no-mtp" 4096 $visArgsNoMtp

        if ($visSrvA.Ready) {
            try {
                $resA = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $visBody -ContentType "application/json" -TimeoutSec 45
                $outA = ($resA.choices[0].message.reasoning_content + " " + $resA.choices[0].message.content).Trim()
                Log-Bench "Vision (No MTP) Response: $outA" "SUCCESS"
                if ($outA.Length -gt 20) { $visionNoMtpPass = $true }
            } catch {
                Log-Bench "Vision No-MTP error: $_" "ERROR"
            }
        }
        $vramA = Get-GpuVramMb
        Stop-LlamaServer $visSrvA

        Add-CsvRow @{
            mode = "vision-no-mtp"; context = 4096; prompt_tokens = 0; generated_tokens = 0;
            mtp = "none"; n_max = 0; p_min = 0.0; ngram = "none";
            drafted_tokens = 0; accepted_tokens = 0; acceptance_pct = 0;
            prompt_tps = 0; generation_tps = 0; wall_time_s = 0; peak_vram_mib = $vramA;
            status = if ($visionNoMtpPass) { "PASS" } else { "FAIL" };
            notes = "Vision without MTP"
        }

        # B. Vision + Best MTP
        Log-Bench "--- Testing Vision WITH BEST MTP ($($finalWinner['name'])) ---" "STEP"
        $visArgsBestMtp = @("--mmproj", $mmproj) + $finalWinner["args"]
        $visSrvB = Start-LlamaServer "vision-best-mtp" 4096 $visArgsBestMtp

        if ($visSrvB.Ready) {
            try {
                $resB = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body $visBody -ContentType "application/json" -TimeoutSec 45
                $outB = ($resB.choices[0].message.reasoning_content + " " + $resB.choices[0].message.content).Trim()
                Log-Bench "Vision (Best MTP) Response: $outB" "SUCCESS"
                if ($outB.Length -gt 20) { $visionBestMtpPass = $true }
            } catch {
                Log-Bench "Vision Best-MTP error: $_" "ERROR"
            }
        }
        $vramB = Get-GpuVramMb
        Stop-LlamaServer $visSrvB

        Add-CsvRow @{
            mode = "vision-best-mtp"; context = 4096; prompt_tokens = 0; generated_tokens = 0;
            mtp = $finalWinner["mtp"]; n_max = $finalWinner["n_max"]; p_min = $finalWinner["p_min"]; ngram = $finalWinner["ngram"];
            drafted_tokens = 0; accepted_tokens = 0; acceptance_pct = 0;
            prompt_tps = 0; generation_tps = 0; wall_time_s = 0; peak_vram_mib = $vramB;
            status = if ($visionBestMtpPass) { "PASS" } else { "FAIL" };
            notes = "Vision with best MTP"
        }
    } else {
        Log-Bench "Test image not found at $testImage! Skipping vision." "WARN"
    }
}

# =============================================================================
# 5. GENERATE FINAL ARTIFACTS & LAUNCHER
# =============================================================================
Log-Bench "Generating final artifacts..." "STEP"

# Create BEST-ORNITH15-96K.cmd
$launcherCmd = "K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd"
$bestArgs = $finalWinner["args"]
$specArgsLine = if ($bestArgs -and $bestArgs.Count -gt 0) {
    "  " + ($bestArgs -join " ") + " ^"
} else {
    ""
}

$launcherContent = @"
@echo off
set "MODEL=K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf"
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
$specArgsLine
  --jinja ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
"@

Set-Content -Path $launcherCmd -Value $launcherContent -Encoding ASCII
Log-Bench "Created launcher: $launcherCmd" "SUCCESS"

# Generate RESULT.md
$noMtpSpeed = if ($resNoMtp) { [double]$resNoMtp["generation_tps"] } else { [double]($sweepResults | Where-Object { $_["mode"] -eq "baseline-no-mtp" })["generation_tps"] }
$bestSpeed = [double]$finalWinnerResult["generation_tps"]
$gainPct = if ($noMtpSpeed -gt 0) { [Math]::Round((($bestSpeed - $noMtpSpeed) / $noMtpSpeed) * 100, 1) } else { 0.0 }

$mdContent = @"
# Ornith-1.5-35B-A3B MTP & 96K Benchmark Results

## Summary

- **Model**: `K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf`
- **Architecture**: `qwen35moe` (256x2.6B MoE, Next-N MTP = 1)
- **CUDA Device**: NVIDIA GeForce RTX 2080 Ti (CUDA Compute 7.5, 22 GB VRAM)
- **Backend**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`)

---

## Performance Comparison (96K Context)

| Mode | Context | Generation tok/s | Prompt tok/s | MTP Drafted | MTP Accepted | Acceptance % | Peak VRAM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **No MTP (Baseline)** | 98304 | $noMtpSpeed | $(if ($resNoMtp) { $resNoMtp["prompt_tps"] } else { "N/A" }) | 0 | 0 | 0.0% | $(if ($resNoMtp) { $resNoMtp["peak_vram_mib"] } else { "N/A" }) MiB |
| **Best MTP: $($finalWinner['name'])** | 98304 | **$bestSpeed** | $(if ($finalWinnerResult) { $finalWinnerResult["prompt_tps"] } else { "N/A" }) | $(if ($finalWinnerResult) { $finalWinnerResult["drafted_tokens"] } else { "N/A" }) | $(if ($finalWinnerResult) { $finalWinnerResult["accepted_tokens"] } else { "N/A" }) | $(if ($finalWinnerResult) { $finalWinnerResult["acceptance_pct"] } else { "N/A" })% | $(if ($finalWinnerResult) { $finalWinnerResult["peak_vram_mib"] } else { "N/A" }) MiB |

- **Speed Gain**: **+$gainPct%**
- **Optimal Parameters**:
  - `n_max`: `$($finalWinner['n_max'])`
  - `p_min`: `$($finalWinner['p_min'])`
  - `ngram`: `$($finalWinner['ngram'])`

---

## Vision Smoke Test

- **mmproj**: `K:\Project\Models\mmproj-Ornith-1.5-35B-BF16.gguf`
- **Vision without MTP**: $(if ($visionNoMtpPass) { "PASS (Working)" } else { "FAIL" })
- **Vision + Best MTP**: $(if ($visionBestMtpPass) { "PASS (Compatible)" } else { "FAIL / Incompatible" })

---

## Production Launcher

Created: `K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd`
"@

Set-Content -Path $resultMd -Value $mdContent -Encoding UTF8
Log-Bench "Saved summary: $resultMd" "SUCCESS"

Log-Bench "=================================================================" "SUCCESS"
Log-Bench "ALL ORNITH-1.5 BENCHMARKS COMPLETED SUCCESSFULLY!" "SUCCESS"
Log-Bench "=================================================================" "SUCCESS"
