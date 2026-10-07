# Sets up the studio on this machine: virtual environment, package, .env. Run from the repository root.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.12+ is required and was not found on PATH." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required and was not found on PATH." }

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
Write-Host "Installing the studio..."
& .\.venv\Scripts\python -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python -m pip install --quiet -e ".[dev,anthropic,redis]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - set SHUNYA_API_TOKEN (and ANTHROPIC_API_KEY for real agents) there."
}

Write-Host ""
& .\.venv\Scripts\shunya doctor
Write-Host ""
Write-Host "Start the studio with:  .\.venv\Scripts\shunya serve"
