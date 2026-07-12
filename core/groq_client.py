"""
GroqClient — singleton wrapper around Groq SDK.

Handles:
- 429 rate limit: reads retry-after header and waits accordingly
- Transient errors: exponential backoff up to MAX_RETRIES
- All failures: returns structured fallback dict, never raises
"""
import re
import time
import logging

from groq import Groq, RateLimitError

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _fallback(reason: str) -> dict:
    return {"error": True, "reason": reason, "text": ""}


def _parse_retry_after(exc_str: str) -> float:
    """Extract retry delay seconds from Groq 429 error message."""
    match = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*s", str(exc_str), re.IGNORECASE)
    if match:
        return min(float(match.group(1)) + 1.0, 60.0)  # cap at 60s
    return 10.0  # default wait


class GroqClient:
    """Singleton Groq wrapper with retry + rate limit handling."""

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
                "GROQ_API_KEY not set. Add it to .env or Streamlit Cloud secrets."
            )
        self._client = Groq(api_key=config.GROQ_API_KEY)
        self._initialised = True

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system_instruction: str | None = None,
    ) -> dict:
        """
        Generate text. Returns:
            {"error": False, "text": "..."}
            {"error": True,  "reason": "...", "text": ""}
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
                return {"error": False, "text": response.choices[0].message.content or ""}

            except RateLimitError as exc:
                wait = _parse_retry_after(str(exc))
                logger.warning(
                    "Groq 429 rate limit on attempt %d — waiting %.1fs", attempt, wait
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                else:
                    return _fallback(f"Rate limit exceeded — please wait and retry. ({exc})")

            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq attempt %d failed: %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE ** attempt)

        return _fallback(f"generate failed after {_MAX_RETRIES} attempts")

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """Groq has no embeddings endpoint — returns None."""
        return None
