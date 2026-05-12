"""Qdrant vector store – stores and queries embeddings for semantic search."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from mysterial.config import settings
from mysterial.models.code import Symbol

logger = logging.getLogger(__name__)

# Qdrant payload field names
_F_ID = "symbol_id"
_F_NAME = "name"
_F_KIND = "kind"
_F_REPO = "repo"
_F_FILE = "file_path"
_F_LANG = "language"
_F_DOC = "docstring"
_F_SIG = "signature"


def _make_point_struct(
    point_id: str, vector: list[float], payload: dict[str, Any]
) -> Any:
    """Build a Qdrant PointStruct, importing lazily to avoid hard dependency at module level."""
    from qdrant_client.models import PointStruct  # type: ignore[import-untyped]

    return PointStruct(id=point_id, vector=vector, payload=payload)


def _make_filter(
    conditions: list[Any],
) -> Any | None:
    """Build a Qdrant Filter from a list of conditions, or return None if empty."""
    if not conditions:
        return None
    from qdrant_client.models import Filter  # type: ignore[import-untyped]

    return Filter(must=conditions)


def _make_field_condition(key: str, value: str) -> Any:
    """Build a Qdrant FieldCondition."""
    from qdrant_client.models import FieldCondition, MatchValue  # type: ignore[import-untyped]

    return FieldCondition(key=key, match=MatchValue(value=value))


class VectorStore:
    """
    Wrapper around the Qdrant client for storing and searching symbol embeddings.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection: str | None = None,
        embedding_dim: int | None = None,
    ) -> None:
        self._host = host or settings.qdrant_host
        self._port = port or settings.qdrant_port
        self._collection = collection or settings.qdrant_collection
        self._dim = embedding_dim or settings.embedding_dim
        self._client: Any = None

    # ── Lifecycle ───────────────────────────────────────────────────────

    def connect(self) -> None:
        from qdrant_client import QdrantClient  # type: ignore[import-untyped]
        from qdrant_client.models import Distance, VectorParams  # type: ignore[import-untyped]

        self._client = QdrantClient(host=self._host, port=self._port)
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d)", self._collection, self._dim
            )
        else:
            logger.info("Using existing Qdrant collection '%s'", self._collection)

    def close(self) -> None:
        self._client = None

    # ── Write operations ─────────────────────────────────────────────────

    def upsert_symbol(self, symbol: Symbol, embedding: list[float]) -> None:
        """Store or update a symbol's embedding and payload."""
        if self._client is None:
            raise RuntimeError("VectorStore.connect() must be called first")

        # Use a deterministic UUID derived from the symbol id so upserts are idempotent
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, symbol.id))
        payload: dict[str, Any] = {
            _F_ID: symbol.id,
            _F_NAME: symbol.name,
            _F_KIND: symbol.kind.value,
            _F_REPO: symbol.repo,
            _F_FILE: symbol.file_path,
            _F_LANG: symbol.language.value,
            _F_DOC: symbol.docstring,
            _F_SIG: symbol.signature,
        }
        point = _make_point_struct(point_id, embedding, payload)
        self._client.upsert(
            collection_name=self._collection,
            points=[point],
        )

    def upsert_doc(self, doc_id: str, title: str, embedding: list[float]) -> None:
        """Store a doc page embedding."""
        if self._client is None:
            raise RuntimeError("VectorStore.connect() must be called first")

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
        payload: dict[str, Any] = {"type": "doc", _F_ID: doc_id, "title": title}
        point = _make_point_struct(point_id, embedding, payload)
        self._client.upsert(
            collection_name=self._collection,
            points=[point],
        )

    # ── Query operations ─────────────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        repo_filter: str | None = None,
        kind_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic nearest-neighbour search.

        Returns a list of payload dicts ranked by cosine similarity.
        """
        if self._client is None:
            raise RuntimeError("VectorStore.connect() must be called first")

        conditions = []
        if repo_filter:
            conditions.append(_make_field_condition(_F_REPO, repo_filter))
        if kind_filter:
            conditions.append(_make_field_condition(_F_KIND, kind_filter))

        query_filter = _make_filter(conditions)

        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            {**hit.payload, "score": hit.score}
            for hit in results
        ]

