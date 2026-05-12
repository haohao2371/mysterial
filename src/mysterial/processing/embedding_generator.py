"""Embedding generator – wraps sentence-transformers for batch vector generation."""

from __future__ import annotations

import logging
from typing import Optional

from mysterial.config import settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Generate dense vector embeddings for text using sentence-transformers.

    The model is loaded lazily on first use to avoid slow startup times when
    running in contexts that don't need embeddings (e.g. tests with mocks).
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.embedding_model
        self._model: object | None = None

    # ── Public API ──────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for *text*."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts."""
        model = self._get_model()
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    @property
    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        return settings.embedding_dim

    # ── Internal helpers ────────────────────────────────────────────────

    def _get_model(self) -> object:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

                logger.info("Loading embedding model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for embedding generation. "
                    "Install it with: pip install sentence-transformers"
                ) from exc
        return self._model

    def build_symbol_text(self, name: str, docstring: str | None, signature: str | None) -> str:
        """Construct the text to embed for a code symbol."""
        parts = [name]
        if signature:
            parts.append(signature)
        if docstring:
            parts.append(docstring)
        return " | ".join(parts)
