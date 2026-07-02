from __future__ import annotations

import os

from ._openai_compatible import OpenAICompatibleClient


class OpenRouterClient(OpenAICompatibleClient):
    def __init__(self):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENROUTER_API_KEY")
        model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            extra_headers={"HTTP-Referer": "https://github.com/Khushir474/redditor"},
        )
