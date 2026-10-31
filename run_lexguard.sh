#!/usr/bin/env bash
# ==============================================================================
# LexGuard Judicial Repository & Verification System — Launcher (.sh)
# Compatible with Git Bash, MSYS2, WSL, macOS, and Linux terminal environments
# ==============================================================================

set -e

# 1. Resolve project directory cleanly across Windows, WSL, and Linux
if [ -f "backend/app/main.py" ]; then
    PROJECT_DIR="$(pwd)"
elif [ -n "${BASH_SOURCE[0]}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/backend/app/main.py" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
elif [ -d "/e/SEM 5 PROJECT/Lexguard" ]; then
    PROJECT_DIR="/e/SEM 5 PROJECT/Lexguard"
elif [ -d "/mnt/e/SEM 5 PROJECT/Lexguard" ]; then
    PROJECT_DIR="/mnt/e/SEM 5 PROJECT/Lexguard"
elif [ -d "E:/SEM 5 PROJECT/Lexguard" ]; then
    PROJECT_DIR="E:/SEM 5 PROJECT/Lexguard"
else
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

cd "${PROJECT_DIR}"

echo "================================================================================"
echo "  ⚖️  LEXGUARD · HIGH COURT & SUPREME COURT JUDICIAL REPOSITORY"
echo "  Project Path: ${PROJECT_DIR}"
echo "================================================================================"

# 2. Detect suitable Python interpreter
PYTHON_CMD=""
if [ -x "${PROJECT_DIR}/backend/venv/bin/python" ]; then
    PYTHON_CMD="${PROJECT_DIR}/backend/venv/bin/python"
elif [ -x "${PROJECT_DIR}/backend/venv/Scripts/python.exe" ]; then
    PYTHON_CMD="${PROJECT_DIR}/backend/venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
elif command -v py >/dev/null 2>&1; then
    PYTHON_CMD="py"
else
    echo "[ERROR] Python interpreter not found in PATH or backend/venv."
    echo "Please ensure Python 3.10+ is installed and available."
    exit 1
fi

echo "[INFO] Using Python: $(${PYTHON_CMD} --version 2>&1)"

# 3. Clean process tracking & termination trap
BACKEND_PID=""
FRONTEND_HTML_PID=""
FRONTEND_VITE_PID=""

cleanup() {
    echo ""
    echo "================================================================================"
    echo "  Shutting down LexGuard judicial services..."
    echo "================================================================================"
    if [ -n "${BACKEND_PID}" ]; then
        kill "${BACKEND_PID}" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_HTML_PID}" ]; then
        kill "${FRONTEND_HTML_PID}" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_VITE_PID}" ]; then
        kill "${FRONTEND_VITE_PID}" 2>/dev/null || true
    fi
    echo "  All services stopped cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 4. Start FastAPI Backend (Port 8000)
echo "[1/3] Starting FastAPI Backend on http://127.0.0.1:8000..."
(
    cd "${PROJECT_DIR}/backend"
    "${PYTHON_CMD}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

# Wait for backend to bind port
sleep 2

# 5. Start HTML5 Judicial Portal (Port 8888)
echo "[2/3] Starting Judicial Portal Server on http://127.0.0.1:8888..."
if [ -d "${PROJECT_DIR}/frontend" ]; then
    (
        cd "${PROJECT_DIR}/frontend"
        "${PYTHON_CMD}" -m http.server 8888 --bind 127.0.0.1
    ) &
    FRONTEND_HTML_PID=$!
elif [ -d "${PROJECT_DIR}/lexguard-html" ]; then
    (
        cd "${PROJECT_DIR}/lexguard-html"
        "${PYTHON_CMD}" -m http.server 8888 --bind 127.0.0.1
    ) &
    FRONTEND_HTML_PID=$!
fi

# Optional: Start Vite React Frontend if node/npm available
if [ -d "${PROJECT_DIR}/frontend" ] && command -v npm >/dev/null 2>&1; then
    if [ -f "${PROJECT_DIR}/frontend/package.json" ]; then
        (
            cd "${PROJECT_DIR}/frontend"
            npm run dev -- --host 127.0.0.1 --port 5173 >/dev/null 2>&1
        ) &
        FRONTEND_VITE_PID=$!
    fi
fi

sleep 2

# 6. Launch Web Browser
PORTAL_URL="http://127.0.0.1:8888/index.html"
echo "[3/3] Opening Judicial Portal in browser: ${PORTAL_URL}"
if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "${PORTAL_URL}" 2>/dev/null || true
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${PORTAL_URL}" 2>/dev/null || true
elif command -v open >/dev/null 2>&1; then
    open "${PORTAL_URL}" 2>/dev/null || true
fi

echo ""
echo "================================================================================"
echo "  ✅ LexGuard Judicial Repository & Verification Platform is Active!"
echo "================================================================================"
echo "  - Judicial Portal:     http://127.0.0.1:8888/index.html"
echo "  - Case Law Search:     http://127.0.0.1:8888/search.html"
echo "  - Case Verification:   http://127.0.0.1:8888/verify.html"
echo "  - Cross-Statutory:     http://127.0.0.1:8888/case-compare.html"
echo "  - Cause List:          http://127.0.0.1:8888/cause-list.html"
echo "  - Registry Workstation:http://127.0.0.1:8888/admin.html?auth_role=staff"
echo "  - FastAPI Backend API: http://127.0.0.1:8000/api/v1/cases"
echo "  - Interactive Swagger: http://127.0.0.1:8000/api/v1/docs"
echo "================================================================================"
echo "  Pre-seeded Judicial Credentials:"
echo "    - Court Staff:     staff@court.gov.in    / staff123"
echo "    - Senior Advocate: advocate@bar.in       / advocate123"
echo "    - Legal Scholar:   scholar@law.edu       / scholar123"
echo "    - Public Citizen:  public@citizen.in     / public123"
echo "================================================================================"
echo "  Press [Ctrl + C] in this terminal to gracefully stop all services."
echo "================================================================================"

# Wait indefinitely until signal received
wait
