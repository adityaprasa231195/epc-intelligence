"""
Central configuration loader.
Reads environment variables from .env and exposes typed constants.
All modules import from here — never from os.environ directly.
Supports both local .env and Streamlit Cloud secrets.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def _get(key: str, default: str = "") -> str:
    """Read from env first, then Streamlit secrets if running on cloud."""
    val = os.environ.get(key, default)
    if val:
        return val
    # Try Streamlit secrets (only available when deployed on Streamlit Cloud)
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

# --- LLM (Groq) ---
GROQ_API_KEY: str = _get("GROQ_API_KEY")
GROQ_TEXT_MODEL: str = _get("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")

# --- RAG ---
CHROMA_COLLECTION_NAME: str = "epc_knowledge_base"
RAG_CHUNK_SIZE: int = 512
RAG_CHUNK_OVERLAP: int = 64
RAG_TOP_K: int = 5

# --- Paths ---
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
SYNTHETIC_DIR: str = os.path.join(DATA_DIR, "synthetic")
STANDARDS_DIR: str = os.path.join(DATA_DIR, "standards")

# --- Schedule Risk ---
RISK_THRESHOLD_DAYS: int = 7

def validate() -> None:
    """Raise early if critical config is missing."""
    if not GROQ_API_KEY:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. Add it to .env or Streamlit Cloud secrets."
        )













