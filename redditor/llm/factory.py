from __future__ import annotations

import logging

from .base import LLMClient

logger = logging.getLogger(__name__)

_client: LLMClient | None = None


def get_llm_client(force_new: bool = False) -> LLMClient:
    """OpenRouter primary, OpenAI fallback on construction/auth error."""
    global _client
    if _client is not None and not force_new:
        return _client

    try:
        from .openrouter_client import OpenRouterClient

        _client = OpenRouterClient()
        return _client
    except Exception as exc:
        logger.warning("OpenRouter client unavailable (%s); falling back to OpenAI.", exc)
        from .openai_client import OpenAIClient

        _client = OpenAIClient()
        return _client
