"""
FastAPI application for Mysterial.

Routes:
  GET  /health                  – liveness / readiness probe
  POST /ingest/repository       – trigger repository indexing
  POST /ingest/openapi          – ingest an OpenAPI spec (JSON/YAML)
  POST /ingest/graphql-schema   – ingest a GraphQL SDL
  GET  /graphql                 – GraphQL playground (browser)
  POST /graphql                 – GraphQL query endpoint
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import strawberry
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter

from mysterial.config import settings
from mysterial.ingestion.api_contract_parser import GraphQLSchemaParser, OpenAPIParser
from mysterial.ingestion.repo_scanner import RepoScanner
from mysterial.ingestion.tree_sitter_parser import TreeSitterParser
from mysterial.models.code import Repository
from mysterial.processing.ast_extractor import ASTExtractor
from mysterial.processing.embedding_generator import EmbeddingGenerator
from mysterial.processing.symbol_linker import SymbolLinker
from mysterial.query.retrieval import KnowledgeRetrieval
from mysterial.query.schema import schema
from mysterial.storage.graph_store import GraphStore
from mysterial.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ── Global service singletons ────────────────────────────────────────────────

_graph = GraphStore()
_vectors = VectorStore()
_embeddings = EmbeddingGenerator()
_retrieval: KnowledgeRetrieval | None = None


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global _retrieval
    logger.info("Connecting to Neo4j and Qdrant …")
    try:
        _graph.connect()
        _vectors.connect()
    except Exception as exc:
        logger.warning(
            "Could not connect to storage services: %s – running in degraded mode", exc
        )
    _retrieval = KnowledgeRetrieval(
        graph=_graph, vectors=_vectors, embeddings=_embeddings
    )
    yield
    _graph.close()


# ── FastAPI app ───────────────────────────────────────────────────────────────


app = FastAPI(
    title="Mysterial – AI Code Knowledge Platform",
    version="0.1.0",
    description=(
        "Internal AI-powered engineering knowledge platform. "
        "Indexes repositories, extracts code structure, maps code↔API↔docs↔tasks, "
        "and exposes MCP tools for AI IDE assistants."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── GraphQL context ───────────────────────────────────────────────────────────


async def get_context() -> dict[str, Any]:
    return {"retrieval": _retrieval}


graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")


# ── REST endpoints ────────────────────────────────────────────────────────────


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# ── Ingestion models ──────────────────────────────────────────────────────────


class IngestRepoRequest(BaseModel):
    url: str
    name: str
    branch: str = "main"


class IngestOpenAPIRequest(BaseModel):
    spec_id: str
    spec: dict[str, Any]  # parsed JSON/YAML spec


class IngestGraphQLRequest(BaseModel):
    spec_id: str
    sdl: str


# ── Ingestion routes ──────────────────────────────────────────────────────────


@app.post("/ingest/repository", tags=["ingestion"])
async def ingest_repository(req: IngestRepoRequest) -> dict[str, Any]:
    """Clone (or update) a repository and index all source files."""
    repo = Repository(name=req.name, url=req.url, branch=req.branch)
    asyncio.create_task(_run_ingestion(repo))
    return {"status": "indexing_started", "repo": req.name}


@app.post("/ingest/openapi", tags=["ingestion"])
async def ingest_openapi(req: IngestOpenAPIRequest) -> dict[str, Any]:
    """Index endpoints from an OpenAPI 2/3 spec dict."""
    parser = OpenAPIParser()
    endpoints = parser.parse_dict(req.spec_id, req.spec)
    if _graph._driver is None:
        raise HTTPException(status_code=503, detail="Graph store not available")
    for ep in endpoints:
        _graph.upsert_endpoint(ep)
    return {"status": "ok", "endpoints_indexed": len(endpoints)}


@app.post("/ingest/graphql-schema", tags=["ingestion"])
async def ingest_graphql_schema(req: IngestGraphQLRequest) -> dict[str, Any]:
    """Index operations from a GraphQL SDL string."""
    parser = GraphQLSchemaParser()
    endpoints = parser.parse(req.spec_id, req.sdl)
    if _graph._driver is None:
        raise HTTPException(status_code=503, detail="Graph store not available")
    for ep in endpoints:
        _graph.upsert_endpoint(ep)
    return {"status": "ok", "operations_indexed": len(endpoints)}


# ── Background ingestion pipeline ────────────────────────────────────────────


async def _run_ingestion(repo: Repository) -> None:
    """Full ingestion pipeline: scan → parse → embed → store."""
    scanner = RepoScanner()
    ts_parser = TreeSitterParser()
    extractor = ASTExtractor()
    linker = SymbolLinker()

    try:
        _graph.upsert_repository(repo)
        all_symbols = []

        for file_record in scanner.register_and_scan(repo):
            try:
                local_path = (
                    repo.local_path + "/" + file_record.path if repo.local_path else None
                )
                if not local_path:
                    continue

                from pathlib import Path

                source = Path(local_path).read_text(encoding="utf-8", errors="replace")

                nodes = ts_parser.parse(source, file_record.language)
                symbols = extractor.extract(
                    nodes, file_record.language, repo.name, file_record.path, source
                )

                for symbol in symbols:
                    # Generate embedding
                    text = _embeddings.build_symbol_text(
                        symbol.name, symbol.docstring, symbol.signature
                    )
                    try:
                        embedding = _embeddings.embed(text)
                        _vectors.upsert_symbol(symbol, embedding)
                    except Exception as exc:
                        logger.warning("Embedding failed for %s: %s", symbol.id, exc)

                    _graph.upsert_symbol(symbol)
                    all_symbols.append(symbol)

            except Exception as exc:
                logger.warning("Failed to process %s: %s", file_record.path, exc)

        # Link symbols within the repository
        for symbol in all_symbols:
            for dep in linker.extract_call_dependencies(symbol, all_symbols):
                try:
                    _graph.upsert_dependency(dep)
                except Exception:
                    pass

        logger.info(
            "Indexing complete for %s: %d symbols", repo.name, len(all_symbols)
        )
    except Exception as exc:
        logger.exception("Ingestion failed for %s: %s", repo.name, exc)


# ── Dev server entry-point ────────────────────────────────────────────────────


def main() -> None:
    import uvicorn

    uvicorn.run(
        "mysterial.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
