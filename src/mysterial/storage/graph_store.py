"""Neo4j graph store – persists symbols and their relationships."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from mysterial.config import settings
from mysterial.models.code import Dependency, Repository, Symbol
from mysterial.models.knowledge import APIEndpoint, DocPage, KnowledgeMapping, Task

logger = logging.getLogger(__name__)


class GraphStore:
    """
    Thin wrapper around the Neo4j Python driver.

    All writes are idempotent (MERGE is used throughout), so it is safe to
    re-index the same repository multiple times.
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver: Any = None

    # ── Lifecycle ───────────────────────────────────────────────────────

    def connect(self) -> None:
        from neo4j import GraphDatabase  # type: ignore[import-untyped]

        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        self._driver.verify_connectivity()
        self._ensure_constraints()
        logger.info("Connected to Neo4j at %s", self._uri)

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    @contextmanager
    def _session(self) -> Generator[Any, None, None]:
        if self._driver is None:
            raise RuntimeError("GraphStore.connect() must be called first")
        with self._driver.session() as session:
            yield session

    # ── Schema / constraints ─────────────────────────────────────────────

    def _ensure_constraints(self) -> None:
        queries = [
            "CREATE CONSTRAINT symbol_id IF NOT EXISTS FOR (s:Symbol) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT repo_name IF NOT EXISTS FOR (r:Repository) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT endpoint_id IF NOT EXISTS FOR (e:Endpoint) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:DocPage) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE",
        ]
        with self._session() as session:
            for q in queries:
                session.run(q)

    # ── Write operations ─────────────────────────────────────────────────

    def upsert_repository(self, repo: Repository) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (r:Repository {name: $name})
                SET r.url = $url, r.branch = $branch, r.last_indexed = $last_indexed
                """,
                name=repo.name,
                url=repo.url,
                branch=repo.branch,
                last_indexed=repo.last_indexed,
            )

    def upsert_symbol(self, symbol: Symbol) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (s:Symbol {id: $id})
                SET s.name = $name,
                    s.qualified_name = $qname,
                    s.kind = $kind,
                    s.language = $language,
                    s.repo = $repo,
                    s.file_path = $file_path,
                    s.line_start = $line_start,
                    s.line_end = $line_end,
                    s.docstring = $docstring,
                    s.signature = $signature
                WITH s
                MATCH (r:Repository {name: $repo})
                MERGE (r)-[:CONTAINS]->(s)
                """,
                id=symbol.id,
                name=symbol.name,
                qname=symbol.qualified_name,
                kind=symbol.kind.value,
                language=symbol.language.value,
                repo=symbol.repo,
                file_path=symbol.file_path,
                line_start=symbol.line_start,
                line_end=symbol.line_end,
                docstring=symbol.docstring,
                signature=symbol.signature,
            )

    def upsert_dependency(self, dep: Dependency) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (a:Symbol {id: $from_id})
                MATCH (b:Symbol {id: $to_id})
                MERGE (a)-[r:DEPENDS_ON {kind: $kind}]->(b)
                """,
                from_id=dep.from_symbol_id,
                to_id=dep.to_symbol_id,
                kind=dep.kind,
            )

    def upsert_endpoint(self, endpoint: APIEndpoint) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (e:Endpoint {id: $id})
                SET e.spec_id = $spec_id,
                    e.method = $method,
                    e.path = $path,
                    e.summary = $summary
                """,
                id=endpoint.id,
                spec_id=endpoint.spec_id,
                method=endpoint.method,
                path=endpoint.path,
                summary=endpoint.summary,
            )

    def upsert_doc_page(self, page: DocPage) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (d:DocPage {id: $id})
                SET d.title = $title, d.url = $url, d.source = $source
                """,
                id=page.id,
                title=page.title,
                url=page.url,
                source=page.source,
            )

    def upsert_task(self, task: Task) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (t:Task {id: $id})
                SET t.key = $key, t.title = $title, t.status = $status, t.source = $source
                """,
                id=task.id,
                key=task.key,
                title=task.title,
                status=task.status,
                source=task.source,
            )

    def upsert_knowledge_mapping(self, mapping: KnowledgeMapping) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (a {id: $from_id})
                MATCH (b {id: $to_id})
                MERGE (a)-[r:MAPPED_TO {kind: $kind}]->(b)
                SET r.confidence = $confidence, r.source = $source
                """,
                from_id=mapping.from_id,
                to_id=mapping.to_id,
                kind=mapping.kind.value,
                confidence=mapping.confidence,
                source=mapping.source,
            )

    # ── Read operations ──────────────────────────────────────────────────

    def get_symbol(self, symbol_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            result = session.run(
                "MATCH (s:Symbol {id: $id}) RETURN s", id=symbol_id
            )
            record = result.single()
            return dict(record["s"]) if record else None

    def find_usages(self, symbol_id: str) -> list[dict[str, Any]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (caller:Symbol)-[:DEPENDS_ON]->(s:Symbol {id: $id})
                RETURN caller
                """,
                id=symbol_id,
            )
            return [dict(r["caller"]) for r in result]

    def get_dependencies(self, symbol_id: str, depth: int = 2) -> list[dict[str, Any]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH path = (s:Symbol {id: $id})-[:DEPENDS_ON*1..$depth]->(dep:Symbol)
                RETURN DISTINCT dep
                """,
                id=symbol_id,
                depth=depth,
            )
            return [dict(r["dep"]) for r in result]

    def get_related_knowledge(self, symbol_id: str) -> dict[str, list[dict[str, Any]]]:
        """Return endpoints, docs, and tasks mapped to a symbol."""
        with self._session() as session:
            endpoints_result = session.run(
                """
                MATCH (s:Symbol {id: $id})-[:MAPPED_TO]->(e:Endpoint)
                RETURN e
                """,
                id=symbol_id,
            )
            docs_result = session.run(
                """
                MATCH (s:Symbol {id: $id})-[:MAPPED_TO]->(d:DocPage)
                RETURN d
                """,
                id=symbol_id,
            )
            tasks_result = session.run(
                """
                MATCH (s:Symbol {id: $id})-[:MAPPED_TO]->(t:Task)
                RETURN t
                """,
                id=symbol_id,
            )
            return {
                "endpoints": [dict(r["e"]) for r in endpoints_result],
                "docs": [dict(r["d"]) for r in docs_result],
                "tasks": [dict(r["t"]) for r in tasks_result],
            }

    def impact_analysis(self, symbol_id: str, depth: int = 3) -> list[dict[str, Any]]:
        """Find all symbols that directly or transitively depend on *symbol_id*."""
        with self._session() as session:
            result = session.run(
                """
                MATCH path = (caller:Symbol)-[:DEPENDS_ON*1..$depth]->(s:Symbol {id: $id})
                RETURN DISTINCT caller
                """,
                id=symbol_id,
                depth=depth,
            )
            return [dict(r["caller"]) for r in result]
