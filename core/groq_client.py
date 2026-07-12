"""
GroqClient — singleton wrapper around Groq SDK (groq-python).

Rules:
- Single instance shared across all agents (module-level singleton).
- Every public method returns a value or a structured fallback dict — never raises.
- Retry: up to MAX_RETRIES attempts with exponential back-off on transient errors.
- Fallback: deterministic error dict so callers can branch without try/except.
"""
import time
import logging
from typing import Any

from groq import Groq

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _fallback(reason: str) -> dict:
    """Structured fallback returned when all retries are exhausted."""
    return {"error": True, "reason": reason, "text": ""}


class GroqClient:
    """
    Thin singleton wrapper around Groq API.
    Usage:
        client = GroqClient()
        result = client.generate("Explain Tier III redundancy")
        if result.get("error"):
            # handle gracefully
    """

    _instance: "GroqClient | None" = None

    def __new__(cls) -> "GroqClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def _init(self) -> None:
        if self._initialised:
            return
        if not config.GROQ_API_KEY:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Run: cp .env.example .env and add your key"
            )
        self._client = Groq(api_key=config.GROQ_API_KEY)
        self._initialised = True

    # ------------------------------------------------------------------
    # Text generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system_instruction: str | None = None,
    ) -> dict:
        """
        Generate a text response via Groq chat completion.

        Returns:
            {"error": False, "text": "<response text>"}
            {"error": True,  "reason": "<msg>", "text": ""}
        """
        self._init()
        model = model or config.GROQ_TEXT_MODEL

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                text = response.choices[0].message.content or ""
                return {"error": False, "text": text}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq generate attempt %d failed: %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE ** attempt)

        return _fallback(f"generate failed after {_MAX_RETRIES} attempts")

    # ------------------------------------------------------------------
    # Embeddings fallback (Groq doesn't natively provide embeddings)
    # For RAG, we'll use a simple keyword-based fallback
    # ------------------------------------------------------------------

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """
        Groq does not provide native embeddings.
        Returning None triggers keyword-based fallback in RAGEngine.
        """
        return None
