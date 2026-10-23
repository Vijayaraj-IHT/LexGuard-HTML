@echo off
setlocal
echo ==========================================================
echo  Lexguard AI Model Downloader - TURBO MODE
echo ==========================================================

set HF_HUB_ENABLE_HF_TRANSFER=1

if exist ".\venv\Scripts\python.exe" (
    set "PYTHON=.\venv\Scripts\python.exe"
    goto :run
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON=python"
    goto :run
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON=py"
    goto :run
)

echo Windows Python not found. Trying WSL Linux...
where wsl >nul 2>nul
if %ERRORLEVEL% equ 0 (
    wsl bash -c "cd '/mnt/e/SEM 5 PROJECT/Lexguard/backend' && [ -f venv/bin/activate ] && source venv/bin/activate; pip install -q hf-transfer huggingface_hub && python download_models.py"
    exit /b %ERRORLEVEL%
)

echo [ERROR] Python not found on Windows or WSL.
pause
exit /b 1

:run
echo [OK] Using Python: %PYTHON%
%PYTHON% -m pip install -q hf-transfer huggingface_hub
%PYTHON% download_models.py
pause
