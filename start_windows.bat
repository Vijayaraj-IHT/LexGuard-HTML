@echo off
chcp 65001 >nul
title LexGuard — High Court Judicial Repository
color 0F

echo ===============================================================================
echo     🏛️  LEXGUARD · HIGH COURT JUDICIAL CASE REPOSITORY & VERIFIER
echo         Pure HTML5 / Bootstrap 5 / FastAPI / PostgreSQL / WebCrypto
echo ===============================================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.10+ from python.org and add it to PATH.
    pause
    exit /b 1
)

:: 2. Setup Virtual Environment if not present
if not exist "backend\venv\Scripts\activate.bat" (
    echo [INFO] Preparing Python virtual environment for Windows in backend\venv...
    if exist "backend\venv\bin" (
        echo [INFO] Detected non-Windows virtual environment. Refreshing backend\venv for Windows...
        rmdir /s /q "backend\venv"
    )
    python -m venv backend\venv
    call backend\venv\Scripts\activate.bat
    echo [INFO] Installing backend dependencies...
    pip install -r backend\requirements.txt
) else (
    call backend\venv\Scripts\activate.bat
)

:: 3. Check or Create backend/.env
if not exist "backend\.env" (
    echo [INFO] Creating backend\.env from example...
    copy backend\.env.example backend\.env >nul
)

:: 4. Start FastAPI Backend (Port 8000)
echo.
echo [1/3] Starting FastAPI Backend on http://127.0.0.1:8000...
start "LexGuard FastAPI Backend (Port 8000)" cmd /k "title LexGuard Backend && cd backend && call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: 5. Start Frontend HTTP Server (Port 8888)
echo [2/3] Starting HTML5 Static Web Server on http://127.0.0.1:8888...
start "LexGuard HTML5 Frontend (Port 8888)" cmd /k "title LexGuard Frontend && cd frontend && python -m http.server 8888"

:: 6. Wait 3 seconds and launch default browser
echo [3/3] Opening High Court Portal in your browser...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8888/index.html

echo.
echo ===============================================================================
echo   ✅ LEXGUARD SERVICES ARE RUNNING!
echo   - High Court Portal:  http://127.0.0.1:8888/index.html
echo   - Case Search:        http://127.0.0.1:8888/search.html
echo   - Staff Workstation:  http://127.0.0.1:8888/admin.html?auth_role=staff
echo   - Interface Gallery:  http://127.0.0.1:8888/screenshots-gallery.html
echo   - FastAPI Swagger UI: http://127.0.0.1:8000/docs
echo.
echo   Press any key in this window to close these launcher tips.
echo   (To stop the servers, close the respective command windows).
echo ===============================================================================
pause >nul
