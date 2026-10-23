#!/usr/bin/env bash
# LexGuard — High Court Judicial Repository Launcher for Linux/macOS

set -e

echo "==============================================================================="
echo "    🏛️  LEXGUARD · HIGH COURT JUDICIAL CASE REPOSITORY & VERIFIER"
echo "        Pure HTML5 / Bootstrap 5 / FastAPI / PostgreSQL 17 / WebCrypto"
echo "==============================================================================="

# 1. Setup virtualenv if needed
if [ ! -d "backend/venv" ]; then
    echo "[INFO] Creating virtualenv..."
    python3 -m venv backend/venv
    source backend/venv/bin/activate
    echo "[INFO] Installing dependencies..."
    pip install -r backend/requirements.txt
else
    source backend/venv/bin/activate
fi

# 2. Setup .env
if [ ! -f "backend/.env" ]; then
    echo "[INFO] Creating backend/.env..."
    cp backend/.env.example backend/.env
fi

# 3. Start Backend
echo "[1/2] Starting FastAPI backend on http://127.0.0.1:8000..."
(cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

# 4. Start Frontend
echo "[2/2] Starting HTML5 frontend on http://127.0.0.1:8888..."
(cd frontend && python -m http.server 8888) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT

echo ""
echo "✅ LexGuard is running!"
echo "   - Portal:  http://127.0.0.1:8888/index.html"
echo "   - Swagger: http://127.0.0.1:8000/docs"
echo "Press [Ctrl+C] to stop all services."

wait
