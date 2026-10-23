# Lexguard Turbo Model Downloader (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Lexguard AI Model Downloader - TURBO MODE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Enable Rust-based multi-threaded transfer engine
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"

# Locate Python binary (Windows venv, system Python, or py launcher)
$PYTHON = $null

if (Test-Path ".\venv\Scripts\python.exe") {
    $PYTHON = ".\venv\Scripts\python.exe"
    Write-Host "[OK] Using Windows Virtual Environment (.\venv\Scripts\python.exe)" -ForegroundColor Green
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PYTHON = "python"
    Write-Host "[OK] Using Python from PATH" -ForegroundColor Green
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PYTHON = "py"
    Write-Host "[OK] Using Python Launcher (py)" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Python was not found in PATH. Please install Python or add it to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Verifying hf-transfer accelerator & huggingface_hub..." -ForegroundColor Cyan
& $PYTHON -m pip install -q hf-transfer huggingface_hub

Write-Host "`nLaunching download pipeline in Turbo Mode..." -ForegroundColor Green
& $PYTHON download_models.py
