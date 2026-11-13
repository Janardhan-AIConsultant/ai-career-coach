"""Embedding provider adapters.

* ``local-hf``: sentence-transformers via ``langchain-huggingface`` (optional, heavy; install
  ``requirements-local-embeddings.txt``). Default model is the 384-d MiniLM used by the old app.
* ``hash``: deterministic feature-hashing bag-of-words (384-d). Lexical only, NOT semantic.
  Intended for tests and offline development, never as a production quality embedding.
Every provider exposes ``model_id`` and ``dimension`` so the vector store can verify that a
collection was built with the same model (mixed dimensions are rejected, not silently mixed).
Errors: ``EmbeddingGenerationError`` (retryable for runtime failures).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import EmbeddingGenerationError


class Embeddings(Protocol):
    model_id: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddings:
    dimension = 384

    def __init__(self) -> None:
        self.model_id = "hash-bow-384"

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9+#.]+", text.lower()):
            h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vec[h % self.dimension] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class LocalHFEmbeddings:
    dimension = 384

    def __init__(self, model_name: str) -> None:
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as exc:
            raise EmbeddingGenerationError(
                "Local embeddings are not installed (see requirements-local-embeddings.txt)"
            ) from exc
        self.model_id = model_name
        self._model = HuggingFaceEmbeddings(model_name=model_name)
        self.dimension = len(self._model.embed_query("dimension probe"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return [list(map(float, v)) for v in self._model.embed_documents(texts)]
        except (RuntimeError, ValueError, OSError) as exc:
            raise EmbeddingGenerationError() from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            return list(map(float, self._model.embed_query(text)))
        except (RuntimeError, ValueError, OSError) as exc:
            raise EmbeddingGenerationError() from exc


def create_embeddings(settings: Settings) -> Embeddings:
    provider = settings.embedding_provider.lower()
    if provider == "hash":
        return HashEmbeddings()
    if provider == "local-hf":
        return LocalHFEmbeddings(settings.embedding_model)
    raise EmbeddingGenerationError(f"Unknown embedding provider: {provider}")
