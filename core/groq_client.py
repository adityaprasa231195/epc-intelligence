import logging

from groq import Groq, RateLimitError

import config

logger = logging.getLogger(__name__)


def _fallback(reason: str) -> dict:
    return {"error": True, "reason": reason, "text": ""}


class GroqClient:

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
        self._init()
        model = model or config.GROQ_TEXT_MODEL

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )
            return {"error": False, "text": response.choices[0].message.content or ""}

        except RateLimitError as exc:
            logger.warning("Groq 429 rate limit — returning fallback: %s", exc)
            return _fallback("Groq rate limit reached. Please wait 1 minute and try again.")

        except Exception as exc:
            logger.warning("Groq call failed: %s", exc)
            return _fallback(str(exc))

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        return None
