# Start Standards Intelligence FastAPI using the repo .venv
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Host "Creating .venv ..."
  python -m venv .venv
  $python = Join-Path $root ".venv\Scripts\python.exe"
}

Write-Host "Installing/updating requirements ..."
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $root "backend\requirements.txt")

if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Warning ".env not found. Copy .env.example to .env and set DATABASE_URL."
}

Set-Location (Join-Path $root "backend")
Write-Host "Starting API on http://0.0.0.0:8000 (docs: /docs) ..."
& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
