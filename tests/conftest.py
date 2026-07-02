from __future__ import annotations

import numpy as np
import pytest

from redditor.db import init_db
from redditor.embeddings.base import EmbeddingClient


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic, hash-based embeddings — no network calls, and identical
    text always yields the identical vector so similarity tests are stable."""

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for text in texts:
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            vectors.append(rng.random(16).astype(np.float32))
        return vectors


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("REDDITOR_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    yield


@pytest.fixture
def fake_embedder(monkeypatch):
    client = FakeEmbeddingClient()
    monkeypatch.setattr("redditor.embeddings.factory.get_embedding_client", lambda force_new=False: client)
    monkeypatch.setattr("redditor.example_store.get_embedding_client", lambda: client)
    monkeypatch.setattr("redditor.safety_gate.get_embedding_client", lambda: client)
    return client
