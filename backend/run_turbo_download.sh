#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=========================================================="
echo " Lexguard AI Model Downloader - TURBO MODE"
echo "=========================================================="

if [ -f "venv/bin/activate" ]; then
    echo "[OK] Activating virtual environment..."
    source venv/bin/activate
fi

export HF_HUB_ENABLE_HF_TRANSFER=1

echo "Installing/verifying hf-transfer..."
pip install -q hf-transfer huggingface_hub

echo "Starting download..."
python download_models.py
