"""
Combined graph + vector retrieval service.

Provides high-level query methods that are used by both the GraphQL resolvers
and the MCP gateway tools.
"""

from __future__ import annotations

import logging
from typing import Any

from mysterial.processing.embedding_generator import EmbeddingGenerator
from mysterial.storage.graph_store import GraphStore
from mysterial.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


class KnowledgeRetrieval:
    """Facade that combines Neo4j graph queries with Qdrant semantic search."""

    def __init__(
        self,
        graph: GraphStore,
        vectors: VectorStore,
        embeddings: EmbeddingGenerator,
    ) -> None:
        self._graph = graph
        self._vectors = vectors
        self._embeddings = embeddings

    # ── Semantic search ──────────────────────────────────────────────────

    def search_code(
        self,
        query: str,
        limit: int = 10,
        repo_filter: str | None = None,
        kind_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic code search: embed *query* and retrieve the nearest symbols.
        """
        query_vector = self._embeddings.embed(query)
        return self._vectors.search(
            query_vector,
            limit=limit,
            repo_filter=repo_filter,
            kind_filter=kind_filter,
        )

    # ── Graph queries ────────────────────────────────────────────────────

    def get_symbol(self, symbol_id: str) -> dict[str, Any] | None:
        return self._graph.get_symbol(symbol_id)

    def find_usages(self, symbol_id: str) -> list[dict[str, Any]]:
        return self._graph.find_usages(symbol_id)

    def get_dependencies(self, symbol_id: str, depth: int = 2) -> list[dict[str, Any]]:
        return self._graph.get_dependencies(symbol_id, depth)

    def analyze_impact(self, symbol_id: str, depth: int = 3) -> list[dict[str, Any]]:
        return self._graph.impact_analysis(symbol_id, depth)

    def get_related_knowledge(self, symbol_id: str) -> dict[str, list[dict[str, Any]]]:
        return self._graph.get_related_knowledge(symbol_id)

    # ── Hybrid search ────────────────────────────────────────────────────

    def recommend(
        self, symbol_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        Recommend related symbols by combining:
        1. Semantic similarity (via vector search using the symbol's own text)
        2. Graph neighbours (direct dependencies and callers)
        """
        symbol = self._graph.get_symbol(symbol_id)
        if not symbol:
            return []

        # Build embedding text from stored fields
        text = self._embeddings.build_symbol_text(
            symbol.get("name", ""),
            symbol.get("docstring"),
            symbol.get("signature"),
        )
        similar = self.search_code(text, limit=limit * 2)

        # Remove the symbol itself
        similar = [s for s in similar if s.get("symbol_id") != symbol_id]

        # Merge with graph neighbours
        deps = self._graph.get_dependencies(symbol_id, depth=1)
        callers = self._graph.find_usages(symbol_id)

        seen: set[str] = {r["symbol_id"] for r in similar}
        for node in deps + callers:
            node_id = node.get("id")
            if node_id and node_id not in seen:
                seen.add(node_id)
                similar.append({**node, "score": 0.5})

        return similar[:limit]
