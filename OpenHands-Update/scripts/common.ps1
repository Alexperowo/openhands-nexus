# Common Helper Module for OpenHands and ik_llama Updaters
# Location: K:\Project\OpenHands-Update\scripts\common.ps1

$Global:ProjectRootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Global:UpdateRootDir = Join-Path $Global:ProjectRootDir "OpenHands-Update"
$Global:LogDir = Join-Path $Global:ProjectRootDir "Logs\Updater"
$Global:BackupDir = Join-Path $Global:UpdateRootDir "backups"

if (-not (Test-Path $Global:LogDir)) { New-Item -ItemType Directory -Path $Global:LogDir -Force | Out-Null }
if (-not (Test-Path $Global:BackupDir)) { New-Item -ItemType Directory -Path $Global:BackupDir -Force | Out-Null }

function Init-UpdaterLog([string]$Component) {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $logFileName = "update-${Component}-${ts}.log"
    $Script:CurrentLogFile = Join-Path $Global:LogDir $logFileName
    return $Script:CurrentLogFile
}

function Mask-Secrets([string]$msg) {
    if (-not $msg) { return "" }
    $clean = $msg -replace '[a-fA-F0-9]{48,64}', '[REDACTED_KEY]'
    $clean = $clean -replace '(?i)(api[_-]?key\s*[:=]\s*["'']?)[^"''\s]+', '$1[REDACTED]'
    $clean = $clean -replace '(?i)(token\s*[:=]\s*["'']?)[^"''\s]+', '$1[REDACTED]'
    return $clean
}

function Log-Msg([string]$Text, [string]$Level = "INFO") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $cleanText = Mask-Secrets $Text
    $formatted = "[$ts] [$Level] $cleanText"

    $color = switch ($Level) {
        "ERROR"   { "Red" }
        "WARN"    { "Yellow" }
        "SUCCESS" { "Green" }
        "STEP"    { "Cyan" }
        "SKIP"    { "DarkGray" }
        Default   { "White" }
    }

    Write-Host $formatted -ForegroundColor $color
    if ($Script:CurrentLogFile) {
        Add-Content -Path $Script:CurrentLogFile -Value $formatted -Encoding UTF8
    }
}

function Get-LatestBackupPath([string]$Component) {
    $compDir = Join-Path $Global:BackupDir $Component
    if (-not (Test-Path $compDir)) { return $null }
    $backups = Get-ChildItem -Path $compDir -Directory | Sort-Object CreationTime -Descending
    if ($backups.Count -gt 0) {
        return $backups[0].FullName
    }
    return $null
}

function Fast-CopyDir([string]$Source, [string]$Dest, [switch]$Mirror) {
    if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest -Force | Out-Null }
    if ($Mirror) {
        robocopy.exe "$Source" "$Dest" /MIR /MT:16 /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
    } else {
        robocopy.exe "$Source" "$Dest" /E /MT:16 /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
    }
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with code $LASTEXITCODE"
    }
}

function Test-ServicePort([int]$Port, [int]$TimeoutSec = 3, [int]$Retries = 5) {
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $wh = $iar.AsyncWaitHandle
            if ($wh.WaitOne($TimeoutSec * 1000, $false)) {
                $client.EndConnect($iar)
                $client.Close()
                return $true
            }
            $client.Close()
        } catch {}
        if ($attempt -lt $Retries) {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Test-HttpEndpoint([string]$Uri, [int]$TimeoutSec = 5, [int]$Retries = 5) {
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            $res = Invoke-WebRequest -Uri $Uri -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
            if ($res.StatusCode -eq 200) {
                return $true
            }
        } catch {}
        if ($attempt -lt $Retries) {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Run-SmokeTest([bool]$CheckLocale = $true) {
    Log-Msg "--- Running OpenHands Platform Smoke Test ---" "STEP"
    $allPass = $true

    # 1. UI :8000
    if (Test-HttpEndpoint "http://localhost:8000") {
        Log-Msg "  [OK] UI http://localhost:8000 is active (HTTP 200)" "SUCCESS"
    } else {
        Log-Msg "  [FAIL] UI http://localhost:8000 is unreachable!" "ERROR"
        $allPass = $false
    }

    # 2. Agent Server :18000
    if (Test-ServicePort 18000) {
        Log-Msg "  [OK] Agent Server listening on port 18000" "SUCCESS"
    } else {
        Log-Msg "  [FAIL] Agent Server port 18000 not responding!" "ERROR"
        $allPass = $false
    }

    # 3. Automation Server :18001
    if (Test-ServicePort 18001) {
        Log-Msg "  [OK] Automation Server listening on port 18001" "SUCCESS"
    } else {
        Log-Msg "  [FAIL] Automation Server port 18001 not responding!" "ERROR"
        $allPass = $false
    }

    # 4. Voice Bridge :18002
    if (Test-HttpEndpoint "http://127.0.0.1:18002/health") {
        Log-Msg "  [OK] Voice Bridge http://127.0.0.1:18002/health is healthy (HTTP 200)" "SUCCESS"
    } else {
        Log-Msg "  [FAIL] Voice Bridge health check failed!" "ERROR"
        $allPass = $false
    }

    # 5. LLM Server :8080
    if (Test-HttpEndpoint "http://127.0.0.1:8080/v1/models") {
        Log-Msg "  [OK] LLM Server http://127.0.0.1:8080/v1/models is active (HTTP 200)" "SUCCESS"
    } else {
        Log-Msg "  [FAIL] LLM Server port 8080 not responding!" "ERROR"
        $allPass = $false
    }

    # 6. Mobile LAN Gateway :8443
    if (Test-ServicePort 8443) {
        Log-Msg "  [OK] Mobile LAN Gateway listening on port 8443" "SUCCESS"
    } else {
        Log-Msg "  [WARN] Mobile LAN Gateway port 8443 is not active" "WARN"
    }

    # 7. Check Locale Parity if requested
    if ($CheckLocale) {
        Log-Msg "  Checking Russian localization dictionary integrity..." "STEP"
        $auditScript = Join-Path $Global:ProjectRootDir "openhands-localization\audit-localization.py"
        if (Test-Path $auditScript) {
            $auditProc = Start-Process -FilePath "python.exe" -ArgumentList "`"$auditScript`"" -NoNewWindow -PassThru -Wait
            if ($auditProc.ExitCode -eq 0) {
                $auditJson = Join-Path $Global:ProjectRootDir "OpenHands-Tests\Russian-Localization\locale-audit.json"
                if (Test-Path $auditJson) {
                    $data = Get-Content $auditJson -Raw | ConvertFrom-Json
                    if ($data.missing_in_ru.Count -eq 0 -and $data.suspicious_matches_count -eq 0) {
                        Log-Msg "  [OK] Locale key parity verified: 0 missing, 0 suspicious matches." "SUCCESS"
                    } else {
                        Log-Msg "  [FAIL] Locale audit reported $($data.missing_in_ru.Count) missing keys!" "ERROR"
                        $allPass = $false
                    }
                }
            } else {
                Log-Msg "  [FAIL] audit-localization.py returned exit code $($auditProc.ExitCode)" "ERROR"
                $allPass = $false
            }
        }
    }

    return $allPass
}

