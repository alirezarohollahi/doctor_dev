$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".\.venv")) {
    py -3 -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"
$Pip = ".\.venv\Scripts\pip.exe"

& $Python -m pip install --upgrade pip
& $Pip install -r requirements.txt
& $Pip install -e .

Write-Host ""
Write-Host "Running local tests..." -ForegroundColor Cyan
& $Python -m pytest -q

Write-Host ""
Write-Host "Install completed." -ForegroundColor Green
Write-Host "Next: .\run-local-windows.ps1"
