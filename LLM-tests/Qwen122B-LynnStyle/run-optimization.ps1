# Autonomous optimization and evaluation runner for Qwen3.5-122B-A10B LynnStyle
# Location: K:\Project\LLM-tests\Qwen122B-LynnStyle\run-optimization.ps1

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  Qwen3.5-122B-A10B LynnStyle Autonomous Optimization Suite" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow

$pythonExe = "python.exe"
if (Test-Path "D:\AI\Butler\venv\Scripts\python.exe") {
    $pythonExe = "D:\AI\Butler\venv\Scripts\python.exe"
}

Write-Host "Using Python: $pythonExe" -ForegroundColor Green
Write-Host "Executing runner_core.py..." -ForegroundColor Green

& $pythonExe "$scriptDir\runner_core.py"
$exitCode = $LASTEXITCODE

Write-Host "Runner completed with exit code $exitCode at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow

if (Test-Path "$scriptDir\BENCHMARKS.csv") {
    Write-Host "`nGenerated Benchmarks:" -ForegroundColor Cyan
    Get-Content "$scriptDir\BENCHMARKS.csv" | Select-Object -First 20
}

exit $exitCode
