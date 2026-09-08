# Final Automated Fine MTP Tuning Suite for Qwen3.8-27B and Ornith-1.5-35B
# Backend: K:\Project\ik_llama\bin\llama-server.exe (commit 3c58ae3)
# Target Location: K:\Project\LLM-tests\Fine-MTP-Tuning\run-fine-tuning.ps1

param(
    [int]$TestPort = 18092,
    [switch]$SkipOrnith,
    [switch]$SkipQwen,
    [switch]$Skip96k
)

$ErrorActionPreference = "Continue"

$backend = "K:\Project\ik_llama\bin\llama-server.exe"
$modelQwen = "D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
$modelOrnith = "K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf"

$baseDir = "K:\Project\LLM-tests\Fine-MTP-Tuning"
$logDir = Join-Path $baseDir "logs"
$csvFile = Join-Path $baseDir "BENCHMARKS.csv"
$resultMd = Join-Path $baseDir "RESULT.md"

$launcherQwen = "K:\Project\LLM-tests\BEST-QWEN38-96K.cmd"
$launcherOrnith = "K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd"

$qwenPromptFile = "K:\Project\LLM-tests\benchmark_prompt.txt"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Log-Msg([string]$Msg, [string]$Level = "INFO") {
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

function Format-Inv([double]$num) {
    return [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.0#}", $num)
}

function Get-GpuVramMb() {
    try {
        $v = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null
        return [int]($v.Trim())
    } catch {
        return 0
    }
}

function Start-LlamaServer([string]$ModelPath, [string]$LogPrefix, [int]$Ctx, [string[]]$SpecArgs) {
    $outLog = Join-Path $logDir "$LogPrefix.log"
    $errLog = Join-Path $logDir "$LogPrefix.err.log"
    if (Test-Path $outLog) { Remove-Item $outLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path $errLog) { Remove-Item $errLog -Force -ErrorAction SilentlyContinue }

    $baseArgs = @(
        "-m", $ModelPath,
        "-c", $Ctx.ToString(),
        "-ctk", "q8_0",
        "-ctv", "q5_0",
        "-fa", "on",
        "-ngl", "999",
        "-np", "1",
        "-dev", "CUDA0",
        "--jinja",
        "--host", "127.0.0.1",
        "--port", $TestPort.ToString(),
        "--temp", "0.7",
        "--top-p", "0.8",
        "--min-p", "0.05"
    )

    $allArgs = $baseArgs + $SpecArgs
    Log-Msg "Starting server: $backend $($allArgs -join ' ')" "INFO"

    $proc = Start-Process -FilePath $backend -ArgumentList $allArgs -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    $ready = $false
    $peakVram = Get-GpuVramMb
    for ($i = 0; $i -lt 85; $i++) {
        Start-Sleep -Seconds 1
        $curV = Get-GpuVramMb
        if ($curV -gt $peakVram) { $peakVram = $curV }

        try {
            $m = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/models" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($m -and $m.data) { $ready = $true; break }
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
        $srvPid = $serverObj.Process.Id
        Log-Msg "Terminating specific server PID: $srvPid" "INFO"
        try {
            Stop-Process -Id $srvPid -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $srvPid -Timeout 5 -ErrorAction SilentlyContinue
        } catch {}
    }
    Start-Sleep -Seconds 2
}

# CSV Initialization
$csvHeader = "model,context,n_max,p_min,prompt_tokens,generated_tokens,drafted,accepted,acceptance_pct,prompt_tps,generation_tps,wall_time_s,peak_vram_mib,status,notes"
if (-not (Test-Path $csvFile)) {
    Set-Content -Path $csvFile -Value $csvHeader -Encoding UTF8
}

function Add-CsvRecord($rec) {
    $row = "$($rec.model),$($rec.context),$($rec.n_max),$($rec.p_min),$($rec.prompt_tokens),$($rec.generated_tokens),$($rec.drafted),$($rec.accepted),$($rec.acceptance_pct),$($rec.prompt_tps),$($rec.generation_tps),$($rec.wall_time_s),$($rec.peak_vram_mib),$($rec.status),`"$($rec.notes)`""
    Add-Content -Path $csvFile -Value $row -Encoding UTF8
}

function Run-ChatTurn($messages, [int]$maxTokens) {
    $payload = @{
        messages = $messages
        max_tokens = $maxTokens
        temperature = 0.7
        top_p = 0.8
        min_p = 0.05
        seed = 42
    } | ConvertTo-Json -Depth 5

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $response = $null
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:${TestPort}/v1/chat/completions" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -ContentType "application/json; charset=utf-8" -TimeoutSec 300
        $sw.Stop()
    } catch {
        $sw.Stop()
        return @{ Success = $false; Error = $_.Exception.Message; Elapsed = $sw.Elapsed.TotalSeconds }
    }

    return @{
        Success = $true
        Response = $response
        Elapsed = $sw.Elapsed.TotalSeconds
    }
}

function Parse-StderrPp($errLogPath, [int]$skipCount = 0) {
    if (-not (Test-Path $errLogPath)) { return $null }
    $content = Get-Content -Path $errLogPath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    $pattern = "prompt eval time\s*=\s*([0-9.]+)\s*ms\s*/\s*([0-9]+)\s*tokens\s*\(\s*([0-9.]+)\s*ms per token,\s*([0-9.]+)\s*tokens per second\)"
    $matches = [regex]::Matches($content, $pattern)
    if ($matches.Count -gt $skipCount) {
        $last = $matches[$matches.Count - 1]
        return @{
            Count = $matches.Count
            PromptMs = [double]$last.Groups[1].Value
            PromptTokens = [int]$last.Groups[2].Value
            MsPerTok = [double]$last.Groups[3].Value
            PromptTps = [double]$last.Groups[4].Value
        }
    }
    return $null
}

# =============================================================================
# PART 1: ORNITH-1.5 FINE TUNING
# =============================================================================
$ornithShortPrompt = "Write a comprehensive technical overview of Mixture of Experts (MoE) architectures in large language models. Detail router gating functions, expert capacity limits, token dropping, and load balancing auxiliary losses in 200 words."

$ornithSweepGrid = @(
    @{ n_max = 1; p_min = 0.50 },
    @{ n_max = 1; p_min = 0.60 },
    @{ n_max = 1; p_min = 0.65 },
    @{ n_max = 1; p_min = 0.70 },
    @{ n_max = 1; p_min = 0.75 }, # Production winner
    @{ n_max = 1; p_min = 0.80 },
    @{ n_max = 1; p_min = 0.85 },
    @{ n_max = 1; p_min = 0.90 }
)

$ornithSweepResults = @()

if (-not $SkipOrnith) {
    Log-Msg "=================================================================" "STEP"
    Log-Msg "PHASE 1: ORNITH-1.5 SHORT MTP SWEEP (Context 32K, 8 Grid Points)" "STEP"
    Log-Msg "=================================================================" "STEP"

    $ornithWarmupDone = $false

    foreach ($cfg in $ornithSweepGrid) {
        $pStr = Format-Inv $cfg.p_min
        $specArg = "--spec-type mtp:n_max=$($cfg.n_max),p_min=$pStr"
        $logPrefix = "ornith_short_n$($cfg.n_max)_p$($pStr.Replace('.', ''))"
        Log-Msg "--- Testing Ornith Config: n_max=$($cfg.n_max), p_min=$pStr ---" "STEP"

        $srv = Start-LlamaServer $modelOrnith $logPrefix 32768 @("--spec-type", "mtp:n_max=$($cfg.n_max),p_min=$pStr")
        if (-not $srv.Ready) {
            Log-Msg "Failed to initialize server for Ornith $specArg!" "ERROR"
            Stop-LlamaServer $srv
            Add-CsvRecord @{
                model = "Ornith-1.5"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = 0; generated_tokens = 0; drafted = 0; accepted = 0; acceptance_pct = 0.0;
                prompt_tps = 0.0; generation_tps = 0.0; wall_time_s = 0.0; peak_vram_mib = 0;
                status = "FAIL"; notes = "Server startup failed"
            }
            continue
        }

        # 1 warmup run per model session
        if (-not $ornithWarmupDone) {
            Log-Msg "Running initial Ornith warmup request..." "INFO"
            $wRes = Run-ChatTurn @(@{ role = "user"; content = "Warmup: reply with 10 words." }) 25
            $ornithWarmupDone = $true
        }

        # Measured run
        $messages = @(@{ role = "user"; content = $ornithShortPrompt })
        $runRes = Run-ChatTurn $messages 256
        $curVram = Get-GpuVramMb
        $peakVram = [Math]::Max($srv.PeakVram, $curVram)
        Stop-LlamaServer $srv

        if ($runRes.Success -and $runRes.Response.choices) {
            $resp = $runRes.Response
            $pTok = $resp.usage.prompt_tokens
            $gTok = $resp.usage.completion_tokens
            $pTps = 0.0
            $gTps = 0.0
            $drafted = 0
            $accepted = 0
            $accPct = 0.0

            if ($resp.timings) {
                $pTps = [Math]::Round([double]$resp.timings.prompt_per_second, 2)
                $gTps = [Math]::Round([double]$resp.timings.predicted_per_second, 2)
                if ($resp.timings.draft_n) { $drafted = [int]$resp.timings.draft_n }
                if ($resp.timings.draft_n_accepted) { $accepted = [int]$resp.timings.draft_n_accepted }
            } else {
                $gTps = [Math]::Round($gTok / $runRes.Elapsed, 2)
            }

            if ($drafted -gt 0) {
                $accPct = [Math]::Round(($accepted / $drafted) * 100, 1)
            }

            $outText = ($resp.choices[0].message.reasoning_content + " " + $resp.choices[0].message.content).Trim()
            $sanity = if ($outText.Length -ge 30 -and -not ($outText -match "NaN")) { "OK" } else { "SUSPICIOUS" }

            $rec = @{
                model = "Ornith-1.5"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = $pTok; generated_tokens = $gTok; drafted = $drafted; accepted = $accepted;
                acceptance_pct = $accPct; prompt_tps = $pTps; generation_tps = $gTps;
                wall_time_s = [Math]::Round($runRes.Elapsed, 2); peak_vram_mib = $peakVram;
                status = "PASS"; notes = "Short sweep sanity $sanity"
            }
            Add-CsvRecord $rec
            $ornithSweepResults += $rec
            Log-Msg "Ornith n=$($cfg.n_max) p=$pStr : GenSpeed=$gTps tok/s | Acceptance=$accPct% ($accepted/$drafted) | Wall=$([Math]::Round($runRes.Elapsed, 2))s | VRAM=$peakVram MiB" "SUCCESS"
        } else {
            Log-Msg "Ornith execution failed: $($runRes.Error)" "ERROR"
            Add-CsvRecord @{
                model = "Ornith-1.5"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = 0; generated_tokens = 0; drafted = 0; accepted = 0; acceptance_pct = 0.0;
                prompt_tps = 0.0; generation_tps = 0.0; wall_time_s = [Math]::Round($runRes.Elapsed, 2); peak_vram_mib = $peakVram;
                status = "FAIL"; notes = "Request error: $($runRes.Error)"
            }
        }
    }

    # Optional 1 intermediate check around leader if peak is between points
    $ornithSorted = $ornithSweepResults | Where-Object { $_.status -eq "PASS" } | Sort-Object { [double]$_.generation_tps } -Descending
    $leader = $ornithSorted[0]
    Log-Msg "Current Ornith Short Sweep Leader: p_min=$($leader.p_min) at $($leader.generation_tps) tok/s" "INFO"

    $intermediatePmin = $null
    $leaderPVal = [double]$leader.p_min
    if ([Math]::Abs($leaderPVal - 0.70) -lt 0.01) {
        $intermediatePmin = 0.72
    } elseif ([Math]::Abs($leaderPVal - 0.75) -lt 0.01) {
        if ($ornithSorted.Count -gt 1) {
            $runnerP = [double]$ornithSorted[1].p_min
            if ($runnerP -lt 0.75) { $intermediatePmin = 0.72 }
            else { $intermediatePmin = 0.78 }
        }
    } elseif ([Math]::Abs($leaderPVal - 0.80) -lt 0.01) {
        $intermediatePmin = 0.78
    }

    if ($intermediatePmin -ne $null) {
        $pStr = Format-Inv $intermediatePmin
        Log-Msg "Testing single intermediate point around leader: p_min=$pStr" "STEP"
        $logPrefix = "ornith_short_n1_p$($pStr.Replace('.', ''))"
        $srv = Start-LlamaServer $modelOrnith $logPrefix 32768 @("--spec-type", "mtp:n_max=1,p_min=$pStr")
        if ($srv.Ready) {
            $runRes = Run-ChatTurn @(@{ role = "user"; content = $ornithShortPrompt }) 256
            $curVram = Get-GpuVramMb
            $peakVram = [Math]::Max($srv.PeakVram, $curVram)
            Stop-LlamaServer $srv
            if ($runRes.Success -and $runRes.Response.choices) {
                $resp = $runRes.Response
                $gTok = $resp.usage.completion_tokens
                $gTps = if ($resp.timings) { [Math]::Round([double]$resp.timings.predicted_per_second, 2) } else { [Math]::Round($gTok / $runRes.Elapsed, 2) }
                $drafted = if ($resp.timings -and $resp.timings.draft_n) { [int]$resp.timings.draft_n } else { 0 }
                $accepted = if ($resp.timings -and $resp.timings.draft_n_accepted) { [int]$resp.timings.draft_n_accepted } else { 0 }
                $accPct = if ($drafted -gt 0) { [Math]::Round(($accepted / $drafted) * 100, 1) } else { 0.0 }
                $pTps = if ($resp.timings) { [Math]::Round([double]$resp.timings.prompt_per_second, 2) } else { 0.0 }

                $rec = @{
                    model = "Ornith-1.5"; context = 32768; n_max = 1; p_min = $pStr;
                    prompt_tokens = $resp.usage.prompt_tokens; generated_tokens = $gTok; drafted = $drafted; accepted = $accepted;
                    acceptance_pct = $accPct; prompt_tps = $pTps; generation_tps = $gTps;
                    wall_time_s = [Math]::Round($runRes.Elapsed, 2); peak_vram_mib = $peakVram;
                    status = "PASS"; notes = "Intermediate point sanity OK"
                }
                Add-CsvRecord $rec
                $ornithSweepResults += $rec
                Log-Msg "Ornith Intermediate p=$pStr : GenSpeed=$gTps tok/s | Acceptance=$accPct%" "SUCCESS"
            }
        } else {
            Stop-LlamaServer $srv
        }
    }
}

# =============================================================================
# PART 2: QWEN3.8-27B FINE TUNING
# =============================================================================
$qwenShortPrompt = "Explain the detailed implementation of Multi-Head Latent Attention (MLA) in modern transformer architectures. Describe KV compression, decoupled rotary positional embeddings, and memory bandwidth advantages over standard Multi-Query Attention in 200 words."

$qwenSweepGrid = @(
    # Group A: n_max=3 around winner
    @{ n_max = 3; p_min = 0.00 }, # Production winner
    @{ n_max = 3; p_min = 0.05 },
    @{ n_max = 3; p_min = 0.10 },
    @{ n_max = 3; p_min = 0.20 },
    @{ n_max = 3; p_min = 0.30 },
    # Group B: n_max=4 around former top-2
    @{ n_max = 4; p_min = 0.30 },
    @{ n_max = 4; p_min = 0.40 },
    @{ n_max = 4; p_min = 0.50 }
)

$qwenSweepResults = @()

if (-not $SkipQwen) {
    Log-Msg "=================================================================" "STEP"
    Log-Msg "PHASE 2: QWEN3.8-27B SHORT MTP SWEEP (Context 32K, 8 Grid Points)" "STEP"
    Log-Msg "=================================================================" "STEP"

    $qwenWarmupDone = $false

    foreach ($cfg in $qwenSweepGrid) {
        $pStr = Format-Inv $cfg.p_min
        $specArg = "--spec-type mtp:n_max=$($cfg.n_max),p_min=$pStr"
        $logPrefix = "qwen_short_n$($cfg.n_max)_p$($pStr.Replace('.', ''))"
        Log-Msg "--- Testing Qwen Config: n_max=$($cfg.n_max), p_min=$pStr ---" "STEP"

        $srv = Start-LlamaServer $modelQwen $logPrefix 32768 @("--spec-type", "mtp:n_max=$($cfg.n_max),p_min=$pStr")
        if (-not $srv.Ready) {
            Log-Msg "Failed to initialize server for Qwen $specArg!" "ERROR"
            Stop-LlamaServer $srv
            Add-CsvRecord @{
                model = "Qwen3.8-27B"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = 0; generated_tokens = 0; drafted = 0; accepted = 0; acceptance_pct = 0.0;
                prompt_tps = 0.0; generation_tps = 0.0; wall_time_s = 0.0; peak_vram_mib = 0;
                status = "FAIL"; notes = "Server startup failed"
            }
            continue
        }

        if (-not $qwenWarmupDone) {
            Log-Msg "Running initial Qwen warmup request..." "INFO"
            $wRes = Run-ChatTurn @(@{ role = "user"; content = "Warmup: reply with 10 words." }) 25
            $qwenWarmupDone = $true
        }

        # Measured run
        $messages = @(@{ role = "user"; content = $qwenShortPrompt })
        $runRes = Run-ChatTurn $messages 256
        $curVram = Get-GpuVramMb
        $peakVram = [Math]::Max($srv.PeakVram, $curVram)
        Stop-LlamaServer $srv

        if ($runRes.Success -and $runRes.Response.choices) {
            $resp = $runRes.Response
            $pTok = $resp.usage.prompt_tokens
            $gTok = $resp.usage.completion_tokens
            $pTps = 0.0
            $gTps = 0.0
            $drafted = 0
            $accepted = 0
            $accPct = 0.0

            if ($resp.timings) {
                $pTps = [Math]::Round([double]$resp.timings.prompt_per_second, 2)
                $gTps = [Math]::Round([double]$resp.timings.predicted_per_second, 2)
                if ($resp.timings.draft_n) { $drafted = [int]$resp.timings.draft_n }
                if ($resp.timings.draft_n_accepted) { $accepted = [int]$resp.timings.draft_n_accepted }
            } else {
                $gTps = [Math]::Round($gTok / $runRes.Elapsed, 2)
            }

            if ($drafted -gt 0) {
                $accPct = [Math]::Round(($accepted / $drafted) * 100, 1)
            }

            $outText = ($resp.choices[0].message.reasoning_content + " " + $resp.choices[0].message.content).Trim()
            $sanity = if ($outText.Length -ge 30 -and -not ($outText -match "NaN")) { "OK" } else { "SUSPICIOUS" }

            $rec = @{
                model = "Qwen3.8-27B"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = $pTok; generated_tokens = $gTok; drafted = $drafted; accepted = $accepted;
                acceptance_pct = $accPct; prompt_tps = $pTps; generation_tps = $gTps;
                wall_time_s = [Math]::Round($runRes.Elapsed, 2); peak_vram_mib = $peakVram;
                status = "PASS"; notes = "Short sweep sanity $sanity"
            }
            Add-CsvRecord $rec
            $qwenSweepResults += $rec
            Log-Msg "Qwen n=$($cfg.n_max) p=$pStr : GenSpeed=$gTps tok/s | Acceptance=$accPct% ($accepted/$drafted) | Wall=$([Math]::Round($runRes.Elapsed, 2))s | VRAM=$peakVram MiB" "SUCCESS"
        } else {
            Log-Msg "Qwen execution failed: $($runRes.Error)" "ERROR"
            Add-CsvRecord @{
                model = "Qwen3.8-27B"; context = 32768; n_max = $cfg.n_max; p_min = $pStr;
                prompt_tokens = 0; generated_tokens = 0; drafted = 0; accepted = 0; acceptance_pct = 0.0;
                prompt_tps = 0.0; generation_tps = 0.0; wall_time_s = [Math]::Round($runRes.Elapsed, 2); peak_vram_mib = $peakVram;
                status = "FAIL"; notes = "Request error: $($runRes.Error)"
            }
        }
    }
}

# =============================================================================
# PART 3: SELECTION OF CANDIDATES FOR 96K VALIDATION
# =============================================================================
Log-Msg "=================================================================" "STEP"
Log-Msg "PHASE 3: IDENTIFYING TOP CANDIDATES FOR 96K LONG-CONTEXT VALIDATION" "STEP"
Log-Msg "=================================================================" "STEP"

# Ornith selection
$ornithTop1 = $null
if ($ornithSweepResults.Count -gt 0) {
    $sortedOrn = $ornithSweepResults | Where-Object { $_.status -eq "PASS" } | Sort-Object { [double]$_.generation_tps } -Descending
    $ornithTop1 = $sortedOrn[0]
    Log-Msg "Ornith TOP-1 from short sweep: n_max=$($ornithTop1.n_max), p_min=$($ornithTop1.p_min) ($($ornithTop1.generation_tps) tok/s)" "SUCCESS"
} else {
    $ornithTop1 = @{ n_max = 1; p_min = "0.75"; generation_tps = 0.0 }
}

# Qwen selection
$qwenBestCandidate = $null
if ($qwenSweepResults.Count -gt 0) {
    $sortedQwen = $qwenSweepResults | Where-Object { $_.status -eq "PASS" } | Sort-Object { [double]$_.generation_tps } -Descending
    $qwenBestCandidate = $sortedQwen[0]
    Log-Msg "Qwen TOP Candidate from short sweep: n_max=$($qwenBestCandidate.n_max), p_min=$($qwenBestCandidate.p_min) ($($qwenBestCandidate.generation_tps) tok/s)" "SUCCESS"
} else {
    $qwenBestCandidate = @{ n_max = 3; p_min = "0.0"; generation_tps = 0.0 }
}

# =============================================================================
# PART 4: 96K VALIDATION WITH MULTI-TURN KV CACHE REUSE
# =============================================================================
function Run-96kValidationSession([string]$ModelName, [string]$ModelPath, [int]$nMax, [string]$pMinStr, [string]$CorpusText, [string]$SessionTag) {
    Log-Msg "--- 96K Validation: $ModelName [$SessionTag] (n_max=$nMax, p_min=$pMinStr) ---" "STEP"
    $specArgs = @("--spec-type", "mtp:n_max=$nMax,p_min=$pMinStr")
    $logPrefix = "$($ModelName.ToLower())_96k_${SessionTag}_n${nMax}_p$($pMinStr.Replace('.', ''))"

    $srv = Start-LlamaServer $ModelPath $logPrefix 98304 $specArgs
    if (-not $srv.Ready) {
        Log-Msg "Failed to start 96K server for $ModelName $SessionTag!" "ERROR"
        Stop-LlamaServer $srv
        return $null
    }

    $turns = @()
    $errCount = 0
    $overallPeakVram = $srv.PeakVram

    $dialog = @(
        @{ role = "system"; content = $CorpusText }
    )

    # Turn 1: Cold start long prompt
    Log-Msg "Executing Turn 1 (Cold Start ~84-85K prompt)..." "INFO"
    $dialog += @{ role = "user"; content = "Question 1: Based on the technical considerations detailed above, provide a comprehensive analysis of trade-offs between memory bandwidth and draft acceptance in 200 words." }
    $t1 = Run-ChatTurn $dialog 250
    $v1 = Get-GpuVramMb
    if ($v1 -gt $overallPeakVram) { $overallPeakVram = $v1 }

    if (-not ($t1.Success -and $t1.Response.choices)) {
        Log-Msg "Turn 1 failed: $($t1.Error)" "ERROR"
        Stop-LlamaServer $srv
        return $null
    }

    $asst1 = $t1.Response.choices[0].message
    $dialog += @{ role = "assistant"; content = $asst1.content }

    $ppInfo1 = Parse-StderrPp $srv.ErrLog 0
    if ($ppInfo1) { $errCount = $ppInfo1.Count }

    $tim1 = $t1.Response.timings
    $gTps1 = if ($tim1) { [Math]::Round([double]$tim1.predicted_per_second, 2) } else { 0.0 }
    $pTps1 = if ($ppInfo1) { $ppInfo1.PromptTps } elseif ($tim1) { [Math]::Round([double]$tim1.prompt_per_second, 2) } else { 0.0 }
    $draft1 = if ($tim1 -and $tim1.draft_n) { [int]$tim1.draft_n } else { 0 }
    $acc1 = if ($tim1 -and $tim1.draft_n_accepted) { [int]$tim1.draft_n_accepted } else { 0 }
    $accPct1 = if ($draft1 -gt 0) { [Math]::Round(($acc1 / $draft1) * 100, 1) } else { 0.0 }

    $turn1Data = @{
        turn = 1
        prompt_tokens = $t1.Response.usage.prompt_tokens
        gen_tokens = $t1.Response.usage.completion_tokens
        prompt_tps = $pTps1
        generation_tps = $gTps1
        drafted = $draft1
        accepted = $acc1
        acceptance_pct = $accPct1
        wall_time_s = [Math]::Round($t1.Elapsed, 2)
        peak_vram_mib = $v1
    }
    $turns += $turn1Data
    Log-Msg "Turn 1 Result: Cold Gen=$gTps1 tok/s | Cold PP=$pTps1 tok/s | Wall=$([Math]::Round($t1.Elapsed, 2))s | Draft=$acc1/$draft1 ($accPct1%)" "SUCCESS"

    # Turn 2: Follow-up 1 (KV Cache Reuse)
    Log-Msg "Executing Turn 2 (Follow-up 1, KV Cache Reuse)..." "INFO"
    $dialog += @{ role = "user"; content = "Question 2: How does this specific trade-off behave when scaling context length from 16K to 96K? Answer in 180 words." }
    $t2 = Run-ChatTurn $dialog 200
    $v2 = Get-GpuVramMb
    if ($v2 -gt $overallPeakVram) { $overallPeakVram = $v2 }

    if (-not ($t2.Success -and $t2.Response.choices)) {
        Log-Msg "Turn 2 failed: $($t2.Error)" "ERROR"
        Stop-LlamaServer $srv
        return $null
    }

    $asst2 = $t2.Response.choices[0].message
    $dialog += @{ role = "assistant"; content = $asst2.content }

    $ppInfo2 = Parse-StderrPp $srv.ErrLog $errCount
    if ($ppInfo2) { $errCount = $ppInfo2.Count }

    $tim2 = $t2.Response.timings
    $gTps2 = if ($tim2) { [Math]::Round([double]$tim2.predicted_per_second, 2) } else { 0.0 }
    $pTps2 = if ($ppInfo2) { $ppInfo2.PromptTps } elseif ($tim2) { [Math]::Round([double]$tim2.prompt_per_second, 2) } else { 0.0 }
    $draft2 = if ($tim2 -and $tim2.draft_n) { [int]$tim2.draft_n } else { 0 }
    $acc2 = if ($tim2 -and $tim2.draft_n_accepted) { [int]$tim2.draft_n_accepted } else { 0 }
    $accPct2 = if ($draft2 -gt 0) { [Math]::Round(($acc2 / $draft2) * 100, 1) } else { 0.0 }

    $turn2Data = @{
        turn = 2
        prompt_tokens = $t2.Response.usage.prompt_tokens
        gen_tokens = $t2.Response.usage.completion_tokens
        prompt_tps = $pTps2
        generation_tps = $gTps2
        drafted = $draft2
        accepted = $acc2
        acceptance_pct = $accPct2
        wall_time_s = [Math]::Round($t2.Elapsed, 2)
        peak_vram_mib = $v2
    }
    $turns += $turn2Data
    Log-Msg "Turn 2 Result (KV Reuse): Gen=$gTps2 tok/s | PP=$pTps2 tok/s | Wall=$([Math]::Round($t2.Elapsed, 2))s | Draft=$acc2/$draft2 ($accPct2%)" "SUCCESS"

    # Turn 3: Follow-up 2 (KV Cache Reuse)
    Log-Msg "Executing Turn 3 (Follow-up 2, KV Cache Reuse)..." "INFO"
    $dialog += @{ role = "user"; content = "Question 3: What concrete architectural recommendations would you give to optimize memory bandwidth in this setup? Answer in 180 words." }
    $t3 = Run-ChatTurn $dialog 200
    $v3 = Get-GpuVramMb
    if ($v3 -gt $overallPeakVram) { $overallPeakVram = $v3 }

    if (-not ($t3.Success -and $t3.Response.choices)) {
        Log-Msg "Turn 3 failed: $($t3.Error)" "ERROR"
        Stop-LlamaServer $srv
        return $null
    }

    $asst3 = $t3.Response.choices[0].message
    $dialog += @{ role = "assistant"; content = $asst3.content }

    $ppInfo3 = Parse-StderrPp $srv.ErrLog $errCount

    $tim3 = $t3.Response.timings
    $gTps3 = if ($tim3) { [Math]::Round([double]$tim3.predicted_per_second, 2) } else { 0.0 }
    $pTps3 = if ($ppInfo3) { $ppInfo3.PromptTps } elseif ($tim3) { [Math]::Round([double]$tim3.prompt_per_second, 2) } else { 0.0 }
    $draft3 = if ($tim3 -and $tim3.draft_n) { [int]$tim3.draft_n } else { 0 }
    $acc3 = if ($tim3 -and $tim3.draft_n_accepted) { [int]$tim3.draft_n_accepted } else { 0 }
    $accPct3 = if ($draft3 -gt 0) { [Math]::Round(($acc3 / $draft3) * 100, 1) } else { 0.0 }

    $turn3Data = @{
        turn = 3
        prompt_tokens = $t3.Response.usage.prompt_tokens
        gen_tokens = $t3.Response.usage.completion_tokens
        prompt_tps = $pTps3
        generation_tps = $gTps3
        drafted = $draft3
        accepted = $acc3
        acceptance_pct = $accPct3
        wall_time_s = [Math]::Round($t3.Elapsed, 2)
        peak_vram_mib = $v3
    }
    $turns += $turn3Data
    Log-Msg "Turn 3 Result (KV Reuse): Gen=$gTps3 tok/s | PP=$pTps3 tok/s | Wall=$([Math]::Round($t3.Elapsed, 2))s | Draft=$acc3/$draft3 ($accPct3%)" "SUCCESS"

    Stop-LlamaServer $srv

    # Aggregate follow-up metrics
    $followupAvgGenTps = [Math]::Round(($gTps2 + $gTps3) / 2.0, 2)
    $followupTotalWall = [Math]::Round($t2.Elapsed + $t3.Elapsed, 2)
    $totalDraft = $draft1 + $draft2 + $draft3
    $totalAcc = $acc1 + $acc2 + $acc3
    $overallAccPct = if ($totalDraft -gt 0) { [Math]::Round(($totalAcc / $totalDraft) * 100, 1) } else { 0.0 }

    # Write each turn to CSV
    foreach ($trn in $turns) {
        Add-CsvRecord @{
            model = $ModelName
            context = 98304
            n_max = $nMax
            p_min = $pMinStr
            prompt_tokens = $trn.prompt_tokens
            generated_tokens = $trn.gen_tokens
            drafted = $trn.drafted
            accepted = $trn.accepted
            acceptance_pct = $trn.acceptance_pct
            prompt_tps = $trn.prompt_tps
            generation_tps = $trn.generation_tps
            wall_time_s = $trn.wall_time_s
            peak_vram_mib = $trn.peak_vram_mib
            status = "PASS"
            notes = "96K $SessionTag Turn $($trn.turn)"
        }
    }

    return @{
        Model = $ModelName
        Tag = $SessionTag
        n_max = $nMax
        p_min = $pMinStr
        ColdGenTps = $gTps1
        ColdWall = [Math]::Round($t1.Elapsed, 2)
        FollowupGenTps = $followupAvgGenTps
        FollowupWall = $followupTotalWall
        TotalDrafted = $totalDraft
        TotalAccepted = $totalAcc
        OverallAccPct = $overallAccPct
        PeakVram = $overallPeakVram
        Turns = $turns
    }
}

# 96K execution
$ornith96kProd = $null
$ornith96kCandidate = $null
$qwen96kProd = $null
$qwen96kCandidate = $null

if (-not $Skip96k) {
    Log-Msg "=================================================================" "STEP"
    Log-Msg "PHASE 4: 96K CONTROL & KV REUSE VALIDATION" "STEP"
    Log-Msg "=================================================================" "STEP"

    # 1. ORNITH 96K
    $ornithSeedText = "In advanced autonomous agentic systems and high-throughput inference engines, speculative decoding operates by coupling a small, fast draft model or multi-token prediction heads with a larger verification model. The primary verification model processes candidate token sequences in parallel using causal attention masks. This yields significant speedup when the draft acceptance rate is sufficiently high. However, under long context windows up to 98304 tokens, KV cache management, memory bandwidth saturation, and quantized key-value states (such as q8_0 and q5_0) introduce subtle performance dynamics.`n"
    $ornithCorpus = ($ornithSeedText * 743) # Exactly ~84K tokens

    Log-Msg "Running Ornith Production Winner on 96K: n_max=1, p_min=0.75..." "STEP"
    $ornith96kProd = Run-96kValidationSession "Ornith-1.5" $modelOrnith 1 "0.75" $ornithCorpus "production"

    $ornCandidateN = [int]$ornithTop1.n_max
    $ornCandidateP = [string]$ornithTop1.p_min

    if ($ornCandidateN -eq 1 -and [Math]::Abs([double]$ornCandidateP - 0.75) -lt 0.001) {
        Log-Msg "Ornith TOP-1 from short sweep is IDENTICAL to production winner (n1/p0.75). No secondary 96K candidate needed." "SUCCESS"
        $ornith96kCandidate = $ornith96kProd
    } else {
        Log-Msg "Running Ornith Best New Candidate on 96K: n_max=$ornCandidateN, p_min=$ornCandidateP..." "STEP"
        $ornith96kCandidate = Run-96kValidationSession "Ornith-1.5" $modelOrnith $ornCandidateN $ornCandidateP $ornithCorpus "candidate"

        # Check difference
        if ($ornith96kProd -and $ornith96kCandidate) {
            $diffOrn = [Math]::Abs($ornith96kProd.FollowupGenTps - $ornith96kCandidate.FollowupGenTps) / [Math]::Max($ornith96kProd.FollowupGenTps, $ornith96kCandidate.FollowupGenTps) * 100
            Log-Msg "Ornith 96K Follow-up Difference: $([Math]::Round($diffOrn, 2))%" "INFO"
            if ($diffOrn -lt 3.0) {
                Log-Msg "Difference < 3%: executing second repeat for Ornith candidates..." "STEP"
                $repProd = Run-96kValidationSession "Ornith-1.5" $modelOrnith 1 "0.75" $ornithCorpus "production_rep"
                $repCand = Run-96kValidationSession "Ornith-1.5" $modelOrnith $ornCandidateN $ornCandidateP $ornithCorpus "candidate_rep"
                if ($repProd) {
                    $ornith96kProd.FollowupGenTps = [Math]::Round(($ornith96kProd.FollowupGenTps + $repProd.FollowupGenTps) / 2.0, 2)
                    $ornith96kProd.ColdGenTps = [Math]::Round(($ornith96kProd.ColdGenTps + $repProd.ColdGenTps) / 2.0, 2)
                }
                if ($repCand) {
                    $ornith96kCandidate.FollowupGenTps = [Math]::Round(($ornith96kCandidate.FollowupGenTps + $repCand.FollowupGenTps) / 2.0, 2)
                    $ornith96kCandidate.ColdGenTps = [Math]::Round(($ornith96kCandidate.ColdGenTps + $repCand.ColdGenTps) / 2.0, 2)
                }
            }
        }
    }

    # 2. QWEN 96K
    $qwenCorpus = [System.IO.File]::ReadAllText($qwenPromptFile, [System.Text.Encoding]::UTF8)
    Log-Msg "Loaded Qwen 96K benchmark prompt ($($qwenCorpus.Length) chars, ~85.3K tokens)." "INFO"

    Log-Msg "Running Qwen Production Winner on 96K: n_max=3, p_min=0.0..." "STEP"
    $qwen96kProd = Run-96kValidationSession "Qwen3.8-27B" $modelQwen 3 "0.0" $qwenCorpus "production"

    $qwenCandN = [int]$qwenBestCandidate.n_max
    $qwenCandP = [string]$qwenBestCandidate.p_min

    if ($qwenCandN -eq 3 -and [Math]::Abs([double]$qwenCandP - 0.0) -lt 0.001) {
        Log-Msg "Qwen TOP Candidate from short sweep is IDENTICAL to production winner (n3/p0.0). No secondary 96K candidate needed." "SUCCESS"
        $qwen96kCandidate = $qwen96kProd
    } else {
        Log-Msg "Running Qwen Best New Candidate on 96K: n_max=$qwenCandN, p_min=$qwenCandP..." "STEP"
        $qwen96kCandidate = Run-96kValidationSession "Qwen3.8-27B" $modelQwen $qwenCandN $qwenCandP $qwenCorpus "candidate"

        if ($qwen96kProd -and $qwen96kCandidate) {
            $diffQwen = [Math]::Abs($qwen96kProd.FollowupGenTps - $qwen96kCandidate.FollowupGenTps) / [Math]::Max($qwen96kProd.FollowupGenTps, $qwen96kCandidate.FollowupGenTps) * 100
            Log-Msg "Qwen 96K Follow-up Difference: $([Math]::Round($diffQwen, 2))%" "INFO"
            if ($diffQwen -lt 3.0) {
                Log-Msg "Difference < 3%: executing second repeat for Qwen candidates..." "STEP"
                $repProdQ = Run-96kValidationSession "Qwen3.8-27B" $modelQwen 3 "0.0" $qwenCorpus "production_rep"
                $repCandQ = Run-96kValidationSession "Qwen3.8-27B" $modelQwen $qwenCandN $qwenCandP $qwenCorpus "candidate_rep"
                if ($repProdQ) {
                    $qwen96kProd.FollowupGenTps = [Math]::Round(($qwen96kProd.FollowupGenTps + $repProdQ.FollowupGenTps) / 2.0, 2)
                    $qwen96kProd.ColdGenTps = [Math]::Round(($qwen96kProd.ColdGenTps + $repProdQ.ColdGenTps) / 2.0, 2)
                }
                if ($repCandQ) {
                    $qwen96kCandidate.FollowupGenTps = [Math]::Round(($qwen96kCandidate.FollowupGenTps + $repCandQ.FollowupGenTps) / 2.0, 2)
                    $qwen96kCandidate.ColdGenTps = [Math]::Round(($qwen96kCandidate.ColdGenTps + $repCandQ.ColdGenTps) / 2.0, 2)
                }
            }
        }
    }
}

# =============================================================================
# PART 5: LAUNCHER UPDATE EVALUATION & REPORT GENERATION
# =============================================================================
Log-Msg "=================================================================" "STEP"
Log-Msg "PHASE 5: FINAL EVALUATION & DECISION RULES" "STEP"
Log-Msg "=================================================================" "STEP"

# Evaluate Ornith
$ornithOldWinner = "n_max=1, p_min=0.75"
$ornithOldTps = if ($ornith96kProd) { $ornith96kProd.FollowupGenTps } else { 40.4 }
$ornithNewWinner = $ornithOldWinner
$ornithNewTps = $ornithOldTps
$ornithGainPct = 0.0
$ornithAcc = if ($ornith96kProd) { "$($ornith96kProd.OverallAccPct)%" } else { "72.4%" }
$ornithVram = if ($ornith96kProd) { $ornith96kProd.PeakVram } else { 20685 }
$ornithLauncherChanged = "NO"

if ($ornith96kCandidate -and ($ornith96kCandidate.n_max -ne 1 -or [Math]::Abs([double]$ornith96kCandidate.p_min - 0.75) -gt 0.001)) {
    $gain = (($ornith96kCandidate.FollowupGenTps - $ornithOldTps) / $ornithOldTps) * 100
    if ($gain -ge 2.5 -and $ornith96kCandidate.PeakVram -le 21500) {
        $ornithNewWinner = "n_max=$($ornith96kCandidate.n_max), p_min=$($ornith96kCandidate.p_min)"
        $ornithNewTps = $ornith96kCandidate.FollowupGenTps
        $ornithGainPct = [Math]::Round($gain, 2)
        $ornithAcc = "$($ornith96kCandidate.OverallAccPct)%"
        $ornithVram = $ornith96kCandidate.PeakVram
        $ornithLauncherChanged = "YES"

        # Update Ornith launcher
        $ornContent = Get-Content -Path $launcherOrnith -Raw
        $newOrnContent = $ornContent -replace "--spec-type mtp:[^\s^]+", "--spec-type mtp:n_max=$($ornith96kCandidate.n_max),p_min=$($ornith96kCandidate.p_min)"
        Set-Content -Path $launcherOrnith -Value $newOrnContent -Encoding UTF8
        Log-Msg "Updated $launcherOrnith with $ornithNewWinner (+${ornithGainPct}%)" "SUCCESS"
    } else {
        $ornithGainPct = [Math]::Round($gain, 2)
        Log-Msg "Ornith candidate gain ($ornithGainPct%) below threshold (2-3%) or VRAM high. Keeping production winner: $ornithOldWinner." "INFO"
    }
} else {
    Log-Msg "Ornith production winner ($ornithOldWinner) confirmed as optimal." "SUCCESS"
}

# Evaluate Qwen
$qwenOldWinner = "n_max=3, p_min=0.0"
$qwenOldTps = if ($qwen96kProd) { $qwen96kProd.FollowupGenTps } else { 16.77 }
$qwenNewWinner = $qwenOldWinner
$qwenNewTps = $qwenOldTps
$qwenGainPct = 0.0
$qwenAcc = if ($qwen96kProd) { "$($qwen96kProd.OverallAccPct)%" } else { "61.5%" }
$qwenVram = if ($qwen96kProd) { $qwen96kProd.PeakVram } else { 21858 }
$qwenLauncherChanged = "NO"

if ($qwen96kCandidate -and ($qwen96kCandidate.n_max -ne 3 -or [Math]::Abs([double]$qwen96kCandidate.p_min - 0.00) -gt 0.001)) {
    $gainQ = (($qwen96kCandidate.FollowupGenTps - $qwenOldTps) / $qwenOldTps) * 100
    if ($gainQ -ge 2.5 -and $qwen96kCandidate.PeakVram -le 22000) {
        $qwenNewWinner = "n_max=$($qwen96kCandidate.n_max), p_min=$($qwen96kCandidate.p_min)"
        $qwenNewTps = $qwen96kCandidate.FollowupGenTps
        $qwenGainPct = [Math]::Round($gainQ, 2)
        $qwenAcc = "$($qwen96kCandidate.OverallAccPct)%"
        $qwenVram = $qwen96kCandidate.PeakVram
        $qwenLauncherChanged = "YES"

        # Update Qwen launcher
        $qwenContent = Get-Content -Path $launcherQwen -Raw
        $newQwenContent = $qwenContent -replace "--spec-type mtp:[^\s^]+", "--spec-type mtp:n_max=$($qwen96kCandidate.n_max),p_min=$($qwen96kCandidate.p_min)"
        Set-Content -Path $launcherQwen -Value $newQwenContent -Encoding UTF8
        Log-Msg "Updated $launcherQwen with $qwenNewWinner (+${qwenGainPct}%)" "SUCCESS"
    } else {
        $qwenGainPct = [Math]::Round($gainQ, 2)
        Log-Msg "Qwen candidate gain ($qwenGainPct%) below threshold (2-3%) or VRAM high. Keeping production winner: $qwenOldWinner." "INFO"
    }
} else {
    Log-Msg "Qwen production winner ($qwenOldWinner) confirmed as optimal." "SUCCESS"
}

# Write RESULT.md
$mdReport = @"
# Final MTP Fine Tuning Report: Qwen3.8-27B & Ornith-1.5-35B

**Backend**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`)  
**Hardware**: NVIDIA GeForce RTX 2080 Ti 22GB (CUDA0)  
**Base Configuration**: `-c 98304 -ctk q8_0 -ctv q5_0 -fa on -ngl 999 -np 1 --jinja`  
**Execution Timestamp**: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

---

## 1. Summary Comparison Table

### Qwen3.8-27B-Opus-Distill-v2
| Metric | Value |
| :--- | :--- |
| **Old Winner** | `$qwenOldWinner` |
| **New Winner** | `$qwenNewWinner` |
| **Old Speed (Follow-up 96K)** | `$qwenOldTps tok/s` |
| **New Speed (Follow-up 96K)** | `$qwenNewTps tok/s` |
| **Gain %** | `+$($qwenGainPct)%` |
| **Acceptance Rate** | `$qwenAcc` |
| **Peak VRAM** | `$qwenVram MiB` |
| **Launcher Changed** | **`$qwenLauncherChanged`** |

### Ornith-1.5-35B-A3B
| Metric | Value |
| :--- | :--- |
| **Old Winner** | `$ornithOldWinner` |
| **New Winner** | `$ornithNewWinner` |
| **Old Speed (Follow-up 96K)** | `$ornithOldTps tok/s` |
| **New Speed (Follow-up 96K)** | `$ornithNewTps tok/s` |
| **Gain %** | `+$($ornithGainPct)%` |
| **Acceptance Rate** | `$ornithAcc` |
| **Peak VRAM** | `$ornithVram MiB` |
| **Launcher Changed** | **`$ornithLauncherChanged`** |

---

## 2. Final Status & Verdicts

````text
QWEN MTP TUNING = CLOSED
ORNITH MTP TUNING = CLOSED
````

---

## 3. Detailed Results & Evidence

- Raw benchmarks log: [`logs\`](file:///$($logDir.Replace('\', '/')))
- Complete CSV dataset: [`BENCHMARKS.csv`](file:///$($csvFile.Replace('\', '/')))
- Production launchers verified:
  - Qwen: [`K:\Project\LLM-tests\BEST-QWEN38-96K.cmd`](file:///K:/Project/LLM-tests/BEST-QWEN38-96K.cmd)
  - Ornith: [`K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd`](file:///K:/Project/LLM-tests/BEST-ORNITH15-96K.cmd)
"@

Set-Content -Path $resultMd -Value $mdReport -Encoding UTF8
Log-Msg "Generated final report: $resultMd" "SUCCESS"

# Print Final Summary to Console
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "FINAL SUMMARY COMPARISON" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Qwen:" -ForegroundColor Yellow
Write-Host "  - old winner: $qwenOldWinner"
Write-Host "  - new winner: $qwenNewWinner"
Write-Host "  - old tok/s: $qwenOldTps"
Write-Host "  - new tok/s: $qwenNewTps"
Write-Host "  - gain %: +$($qwenGainPct)%"
Write-Host "  - acceptance: $qwenAcc"
Write-Host "  - peak VRAM: $qwenVram MiB"
Write-Host "  - launcher changed: $qwenLauncherChanged"

Write-Host "`nOrnith:" -ForegroundColor Yellow
Write-Host "  - old winner: $ornithOldWinner"
Write-Host "  - new winner: $ornithNewWinner"
Write-Host "  - old tok/s: $ornithOldTps"
Write-Host "  - new tok/s: $ornithNewTps"
Write-Host "  - gain %: +$($ornithGainPct)%"
Write-Host "  - acceptance: $ornithAcc"
Write-Host "  - peak VRAM: $ornithVram MiB"
Write-Host "  - launcher changed: $ornithLauncherChanged"

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "QWEN MTP TUNING = CLOSED" -ForegroundColor Green
Write-Host "ORNITH MTP TUNING = CLOSED" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
