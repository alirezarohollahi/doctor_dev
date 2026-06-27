$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Virtualenv not found. Run .\install-windows.ps1 first." -ForegroundColor Red
    exit 1
}

& $Python .\scripts\reset_and_start.py
