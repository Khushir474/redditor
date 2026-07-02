from __future__ import annotations

import os

import httpx
import numpy as np

from .base import EmbeddingClient


class VoyageEmbeddingClient(EmbeddingClient):
    def __init__(self):
        self.api_key = os.environ.get("VOYAGE_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing VOYAGE_API_KEY")
        self.model = os.environ.get("VOYAGE_MODEL", "voyage-3")

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        resp = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"input": texts, "model": self.model},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [np.array(d["embedding"], dtype=np.float32) for d in data]
