from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[np.ndarray]:
        """Return one embedding vector per input text."""

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def vector_to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
