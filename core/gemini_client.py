"""
GeminiClient — singleton wrapper around google-genai SDK.

Rules:
- Single instance shared across all agents (module-level singleton).
- Every public method returns a value or a structured fallback dict — never raises.
- Retry: up to MAX_RETRIES attempts with exponential back-off on transient errors.
- Fallback: deterministic error dict so callers can branch without try/except.
"""
import time
import logging
from typing import Any

import google.genai as genai
from google.genai import types as genai_types

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _fallback(reason: str) -> dict:
    """Structured fallback returned when all retries are exhausted."""
    return {"error": True, "reason": reason, "text": ""}


class GeminiClient:
    """
    Thin singleton wrapper.
    Usage:
        client = GeminiClient()
        result = client.generate("Explain Tier III redundancy")
        if result.get("error"):
            # handle gracefully
    """

    _instance: "GeminiClient | None" = None

    def __new__(cls) -> "GeminiClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def _init(self) -> None:
        if self._initialised:
            return
        if not config.GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY not set. Run: cp .env.example .env"
            )
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
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
        Generate a text response.

        Returns:
            {"error": False, "text": "<response text>"}
            {"error": True,  "reason": "<msg>", "text": ""}
        """
        self._init()
        model = model or config.GEMINI_TEXT_MODEL

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                kwargs: dict[str, Any] = {}
                if system_instruction:
                    kwargs["config"] = genai_types.GenerateContentConfig(
                        system_instruction=system_instruction
                    )
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    **kwargs,
                )
                return {"error": False, "text": response.text or ""}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini generate attempt %d failed: %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE ** attempt)

        return _fallback(f"generate failed after {_MAX_RETRIES} attempts")

    # ------------------------------------------------------------------
    # Multimodal (text + image)
    # ------------------------------------------------------------------

    def generate_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/png",
        model: str | None = None,
    ) -> dict:
        """
        Generate a response from a text prompt + image bytes.

        Returns same shape as generate().
        """
        self._init()
        model = model or config.GEMINI_TEXT_MODEL

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                image_part = genai_types.Part.from_bytes(
                    data=image_bytes, mime_type=mime_type
                )
                response = self._client.models.generate_content(
                    model=model,
                    contents=[prompt, image_part],
                )
                return {"error": False, "text": response.text or ""}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini multimodal attempt %d failed: %s", attempt, exc
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE ** attempt)

        return _fallback(f"generate_multimodal failed after {_MAX_RETRIES} attempts")

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """
        Return a float embedding vector, or None on failure.
        Callers must handle None and activate keyword fallback.
        """
        self._init()
        model = model or config.GEMINI_EMBEDDING_MODEL

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.models.embed_content(
                    model=model,
                    contents=text,
                )
                return response.embeddings[0].values
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini embed attempt %d failed: %s", attempt, exc
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE ** attempt)

        return None
