from __future__ import annotations

import os

from .base import EmbeddingClient

_client: EmbeddingClient | None = None


def get_embedding_client(force_new: bool = False) -> EmbeddingClient:
    """Selected via EMBEDDING_PROVIDER env var: "voyage" (default) or "openai"."""
    global _client
    if _client is not None and not force_new:
        return _client

    provider = os.environ.get("EMBEDDING_PROVIDER", "voyage").lower()
    if provider == "openai":
        from .openai_client import OpenAIEmbeddingClient

        _client = OpenAIEmbeddingClient()
    elif provider == "voyage":
        from .voyage_client import VoyageEmbeddingClient

        _client = VoyageEmbeddingClient()
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider!r} (expected 'voyage' or 'openai')")
    return _client
