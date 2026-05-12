"""Strawberry GraphQL schema for the Mysterial knowledge query service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import strawberry
from strawberry.types import Info

if TYPE_CHECKING:
    from mysterial.query.retrieval import KnowledgeRetrieval


@strawberry.type
class SymbolResult:
    id: str
    name: str
    kind: str
    language: str
    repo: str
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str]
    signature: Optional[str]
    score: Optional[float]


@strawberry.type
class RelatedKnowledge:
    endpoints: list[str]
    docs: list[str]
    tasks: list[str]


@strawberry.type
class Query:
    @strawberry.field(description="Semantic code search across all indexed repositories.")
    def search_code(
        self,
        info: Info,
        query: str,
        limit: int = 10,
        repo: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> list[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        hits = retrieval.search_code(query, limit=limit, repo_filter=repo, kind_filter=kind)
        return [_hit_to_symbol(h) for h in hits]

    @strawberry.field(description="Look up a specific symbol by its unique ID.")
    def get_symbol(self, info: Info, symbol_id: str) -> Optional[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        node = retrieval.get_symbol(symbol_id)
        if node is None:
            return None
        return _node_to_symbol(node)

    @strawberry.field(description="Find all symbols that call or import the given symbol.")
    def find_usages(self, info: Info, symbol_id: str) -> list[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        return [_node_to_symbol(n) for n in retrieval.find_usages(symbol_id)]

    @strawberry.field(description="Transitive dependency graph for a symbol.")
    def get_dependencies(
        self, info: Info, symbol_id: str, depth: int = 2
    ) -> list[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        return [_node_to_symbol(n) for n in retrieval.get_dependencies(symbol_id, depth)]

    @strawberry.field(
        description="Find all symbols that would be affected by changing the given symbol."
    )
    def analyze_impact(
        self, info: Info, symbol_id: str, depth: int = 3
    ) -> list[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        return [_node_to_symbol(n) for n in retrieval.analyze_impact(symbol_id, depth)]

    @strawberry.field(description="Get API endpoints, docs, and tasks linked to a symbol.")
    def get_related_knowledge(self, info: Info, symbol_id: str) -> RelatedKnowledge:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        related = retrieval.get_related_knowledge(symbol_id)
        return RelatedKnowledge(
            endpoints=[e.get("id", "") for e in related.get("endpoints", [])],
            docs=[d.get("id", "") for d in related.get("docs", [])],
            tasks=[t.get("id", "") for t in related.get("tasks", [])],
        )

    @strawberry.field(
        description="Recommend related symbols using hybrid graph + semantic search."
    )
    def recommend(self, info: Info, symbol_id: str, limit: int = 5) -> list[SymbolResult]:
        retrieval: KnowledgeRetrieval = info.context["retrieval"]
        return [_hit_to_symbol(h) for h in retrieval.recommend(symbol_id, limit)]


# ── Helper converters ────────────────────────────────────────────────────────


def _hit_to_symbol(hit: dict) -> SymbolResult:  # type: ignore[type-arg]
    return SymbolResult(
        id=hit.get("symbol_id", ""),
        name=hit.get("name", ""),
        kind=hit.get("kind", ""),
        language=hit.get("language", ""),
        repo=hit.get("repo", ""),
        file_path=hit.get("file_path", ""),
        line_start=hit.get("line_start", 0),
        line_end=hit.get("line_end", 0),
        docstring=hit.get("docstring"),
        signature=hit.get("signature"),
        score=hit.get("score"),
    )


def _node_to_symbol(node: dict) -> SymbolResult:  # type: ignore[type-arg]
    return SymbolResult(
        id=node.get("id", ""),
        name=node.get("name", ""),
        kind=node.get("kind", ""),
        language=node.get("language", ""),
        repo=node.get("repo", ""),
        file_path=node.get("file_path", ""),
        line_start=node.get("line_start", 0),
        line_end=node.get("line_end", 0),
        docstring=node.get("docstring"),
        signature=node.get("signature"),
        score=None,
    )


schema = strawberry.Schema(query=Query)
