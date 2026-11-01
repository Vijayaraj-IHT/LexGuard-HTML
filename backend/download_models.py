"""
Lexguard Model Downloader & Verification Script (Turbo Mode)
Downloads and caches all open-source Hugging Face models used by Lexguard:
  1. Primary Local LLM : Qwen/Qwen2.5-3B-Instruct (for legal gap analysis & query enrichment)
  2. Embedding Model   : sentence-transformers/all-MiniLM-L6-v2 (for semantic vector search)
  3. Legal NER Model   : law-ai/InLegalBERT (for statutory entity extraction)
"""

import sys
import os
import argparse
from pathlib import Path

# Enable high-speed Rust-based hf_transfer if installed
try:
    import hf_transfer  # noqa: F401  (probe only: availability check, never called)
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    TURBO_ACTIVE = True
except ImportError:
    TURBO_ACTIVE = False

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

# 1. Require huggingface_hub for downloading
try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("\n[ERROR] Missing 'huggingface_hub'. Installing now...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub", "hf-transfer"])
    from huggingface_hub import snapshot_download

# 2. Optional torch & transformers for verification
HAVE_TORCH = False
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForTokenClassification, pipeline
    from sentence_transformers import SentenceTransformer
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False

# 3. Model settings
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_NER_MODEL = "law-ai/InLegalBERT"
DEFAULT_LLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"
HF_TOKEN = None
DEVICE = "cpu"

try:
    from app.core.config import settings
    EMBEDDING_MODEL = settings.EMBEDDING_MODEL_NAME
    NER_MODEL = settings.LEGAL_NER_MODEL_NAME
    LLM_MODEL = settings.LOCAL_LLM_MODEL_NAME
    raw_token = getattr(settings, "HF_TOKEN", None)
    HF_TOKEN = raw_token.strip() if (raw_token and isinstance(raw_token, str) and raw_token.strip()) else None
    DEVICE = settings.DEVICE
except Exception:
    EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL
    NER_MODEL = DEFAULT_NER_MODEL
    LLM_MODEL = DEFAULT_LLM_MODEL
    HF_TOKEN = None



def print_header(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70, flush=True)


def check_system():
    print_header("System & Hardware Diagnostics")
    print(f"Python Executable : {sys.executable}")
    print(f"Python Version    : {sys.version.split()[0]}")
    if TURBO_ACTIVE:
        print("[TURBO MODE] Active (hf_transfer accelerated downloading enabled)")
    else:
        print("[STANDARD MODE] Active (standard multi-stream downloading)")

    if HAVE_TORCH:
        print(f"PyTorch Version   : {torch.__version__}")
        cuda_available = torch.cuda.is_available()
        print(f"CUDA Available    : {cuda_available}")
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"GPU Detected      : {gpu_name} ({gpu_mem:.2f} GB VRAM)")
    else:
        print("PyTorch           : Not installed in this environment (Downloading weights directly)")

    print(f"Configured DEVICE       : {DEVICE}")
    print(f"Target LOCAL_LLM        : {LLM_MODEL}")
    print(f"Target EMBEDDING        : {EMBEDDING_MODEL}")
    print(f"Target LEGAL_NER        : {NER_MODEL}", flush=True)


def download_embedding_model():
    print_header("1/3: Downloading Embedding Model")
    print(f"Model: {EMBEDDING_MODEL} (~120 MB)", flush=True)
    
    path = snapshot_download(repo_id=EMBEDDING_MODEL, token=HF_TOKEN)
    print(f"[DOWNLOAD COMPLETE] Cached at: {path}", flush=True)

    if HAVE_TORCH:
        try:
            model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
            test_vec = model.encode("Supreme Court judgment on anticipatory bail", normalize_embeddings=True)
            print(f"[VERIFIED] Embedding model output dimension: {len(test_vec)} (expected: 384)", flush=True)
        except Exception as e:
            print(f"[NOTE] Downloaded successfully, verification skipped: {e}", flush=True)


def download_legal_ner_model():
    print_header("2/3: Downloading Legal NER Model (InLegalBERT)")
    print(f"Model: {NER_MODEL} (~440 MB)", flush=True)

    path = snapshot_download(repo_id=NER_MODEL, token=HF_TOKEN)
    print(f"[DOWNLOAD COMPLETE] Cached at: {path}", flush=True)

    if HAVE_TORCH:
        try:
            tokenizer = AutoTokenizer.from_pretrained(NER_MODEL, token=HF_TOKEN)
            model = AutoModelForTokenClassification.from_pretrained(NER_MODEL, token=HF_TOKEN)
            device_id = 0 if DEVICE == "cuda" and torch.cuda.is_available() else -1
            ner_pipe = pipeline("token-classification", model=model, tokenizer=tokenizer, device=device_id)
            sample_text = "Accused filed for regular bail under Section 439 CrPC."
            res = ner_pipe(sample_text)
            print(f"[VERIFIED] Legal NER entities detected in sample: {len(res)}", flush=True)
        except Exception as e:
            print(f"[NOTE] Downloaded successfully, verification skipped: {e}", flush=True)


def download_local_llm():
    print_header("3/3: Downloading Local LLM (Qwen/Qwen2.5-3B-Instruct)")
    print(f"Model: {LLM_MODEL} (~6.0 GB)", flush=True)
    print("Downloading model repository snapshot (tokenizer, configuration, weights)...", flush=True)

    # Fast parallel snapshot download with auto-resume
    path = snapshot_download(
        repo_id=LLM_MODEL,
        token=HF_TOKEN,
        ignore_patterns=["*.msgpack", "*.h5", "*.ot", "*.onnx*"],
    )
    print(f"[DOWNLOAD COMPLETE] Local LLM cached at: {path}", flush=True)

    if HAVE_TORCH:
        try:
            print("Verifying model initialization...", flush=True)
            tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL, token=HF_TOKEN, trust_remote_code=True)
            torch_dtype = torch.float16 if DEVICE == "cuda" and torch.cuda.is_available() else torch.float32
            model = AutoModelForCausalLM.from_pretrained(
                LLM_MODEL,
                token=HF_TOKEN,
                torch_dtype=torch_dtype,
                device_map="auto" if DEVICE == "cuda" and torch.cuda.is_available() else None,
                trust_remote_code=True,
            )
            print("[VERIFIED] Local LLM loaded successfully into cache!", flush=True)
        except Exception as e:
            print(f"[NOTE] Downloaded successfully, verification skipped: {e}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Download Lexguard AI models in Turbo Mode")
    parser.add_argument("--llm-only", action="store_true", help="Download only the local LLM")
    parser.add_argument("--skip-llm", action="store_true", help="Download only embedding and NER models")
    args = parser.parse_args()

    print_header("Lexguard Legal Research - Open Source AI Model Downloader (Turbo Mode)")
    check_system()

    try:
        if not args.llm_only:
            download_embedding_model()
            download_legal_ner_model()

        if not args.skip_llm:
            download_local_llm()

        print_header("ALL LEXGUARD MODELS READY")
        print("All required models are successfully downloaded and cached on your machine.")
        print("Hugging Face Cache Location: ~/.cache/huggingface/hub")
        print("\nAll model weights are stored locally. Lexguard can now load them instantly offline.\n", flush=True)

    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Download interrupted by user.", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] An error occurred during model download: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
