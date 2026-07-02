from __future__ import annotations

import json

import httpx

from .base import ANALYZE_SYSTEM_PROMPT, DRAFT_SYSTEM_PROMPT, LLMClient


class OpenAICompatibleClient(LLMClient):
    """Shared implementation for any provider exposing an OpenAI-style
    /chat/completions endpoint (OpenRouter, OpenAI itself, etc)."""

    def __init__(self, base_url: str, api_key: str, model: str, extra_headers: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.extra_headers = extra_headers or {}

    def _chat_json(self, system_prompt: str, user_content: str) -> dict:
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **self.extra_headers,
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def analyze_post(self, post_title: str, post_desc: str, thread_comments: list[str], subreddit: str) -> dict:
        user_content = json.dumps(
            {
                "subreddit": subreddit,
                "post_title": post_title,
                "post_desc": post_desc,
                "top_comments": thread_comments,
            }
        )
        return self._chat_json(ANALYZE_SYSTEM_PROMPT, user_content)

    def draft_comment(
        self,
        post_title: str,
        post_desc: str,
        analysis: dict,
        examples: list[dict],
        ground_truth_context: str | None = None,
    ) -> dict:
        user_content = json.dumps(
            {
                "post_title": post_title,
                "post_desc": post_desc,
                "analysis": analysis,
                "examples": examples,
                "ground_truth_context": ground_truth_context,
            }
        )
        return self._chat_json(DRAFT_SYSTEM_PROMPT, user_content)
