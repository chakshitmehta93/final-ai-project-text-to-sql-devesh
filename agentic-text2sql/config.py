import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ── database ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/college.db").strip()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}").strip()

# ── llm ───────────────────────────────────────────────────────────────────────
# Supported backends: "colab", "ollama", "huggingface", "smart_local"
LLM_BACKEND = os.getenv("LLM_BACKEND", "colab").strip().lower()
AUTO_FALLBACK = os.getenv("AUTO_FALLBACK", "true").strip().lower() in ("1", "true", "yes")

# Colab API — fine-tuned Qwen 1.5B + LoRA adapter over FastAPI + ngrok
COLAB_API_URL = os.getenv("COLAB_API_URL", "").strip().rstrip("/")
COLAB_API_TOKEN = os.getenv("COLAB_API_TOKEN", "").strip()

# Ollama configuration
OLLAMA_FINETUNED_MODEL = "text-to-sql-qwen2.5-coder:7b"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", OLLAMA_FINETUNED_MODEL).strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")

# Hugging Face configuration (1.5B for fast local Mac/CPU inference; 7B for GPU)
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-Coder-1.5B-Instruct").strip()
HF_FINETUNED = "finetune/out/merged"

# ── rag ───────────────────────────────────────────────────────────────────────
EMBED_MODEL = "all-MiniLM-L6-v2"
CHROMA_DIR = "data/chroma"
RAG_TOP_K = 3
RAG_EXPAND_FK = True

# ── pipeline ──────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
MAX_ROWS = 200
QUERY_TIMEOUT = 30

# ── data files ────────────────────────────────────────────────────────────────
RULES_PATH = "data/business_rules.md"
EXAMPLES_PATH = "data/examples.json"


def best_hf_model():
    """Return fine-tuned model if available, otherwise base model."""
    return HF_FINETUNED if os.path.isdir(HF_FINETUNED) else HF_MODEL


def validate_config():
    """Validate configuration for the selected backend."""
    if LLM_BACKEND == "colab":
        if not COLAB_API_URL:
            raise ValueError("COLAB_API_URL is missing from .env")
        if not COLAB_API_TOKEN:
            raise ValueError("COLAB_API_TOKEN is missing from .env")
    elif LLM_BACKEND == "ollama":
        if not OLLAMA_URL:
            raise ValueError("OLLAMA_URL is missing")
    elif LLM_BACKEND == "huggingface":
        if not HF_MODEL:
            raise ValueError("HF_MODEL is missing")
    else:
        raise ValueError(f"Unsupported LLM_BACKEND: {LLM_BACKEND}")
