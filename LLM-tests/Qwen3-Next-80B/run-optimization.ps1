# Autonomous optimization and evaluation runner for Qwen3-Next-80B-A3B-Thinking
# Location: K:\Project\LLM-tests\Qwen3-Next-80B\run-optimization.ps1

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   Qwen3-Next-80B-A3B-Thinking Autonomous Optimization Suite     " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow

$pythonExe = "python.exe"
if (Test-Path "D:\AI\Butler\venv\Scripts\python.exe") {
    $pythonExe = "D:\AI\Butler\venv\Scripts\python.exe"
}

Write-Host "Using Python: $pythonExe" -ForegroundColor Green
Write-Host "Executing runner_qwen80b.py..." -ForegroundColor Green

& $pythonExe "$scriptDir\runner_qwen80b.py"
$exitCode = $LASTEXITCODE

Write-Host "Runner completed with exit code $exitCode at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow

if (Test-Path "$scriptDir\BENCHMARKS.csv") {
    Write-Host "`nGenerated Benchmarks:" -ForegroundColor Cyan
    Get-Content "$scriptDir\BENCHMARKS.csv" | Select-Object -First 25
}

exit $exitCode
