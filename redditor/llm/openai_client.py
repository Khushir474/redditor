from __future__ import annotations

import os

from ._openai_compatible import OpenAICompatibleClient


class OpenAIClient(OpenAICompatibleClient):
    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        super().__init__(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model,
        )
