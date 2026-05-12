"""
MCP Gateway – exposes Mysterial knowledge tools via the Model Context Protocol.

Supported transports:
  • stdio   – for local Cursor / Claude Code integration
  • SSE     – for remote connections (run with --transport sse)

Tools exposed:
  search_code         Semantic search across all indexed code
  get_symbol          Retrieve full metadata for a symbol
  find_usages         Find callers / importers of a symbol
  get_dependencies    Transitive dependency graph
  analyze_impact      Reverse-dependency impact analysis
  get_related_docs    API endpoints, docs, and tasks linked to a symbol
  recommend           Hybrid graph + vector recommendations
  index_repository    Trigger background ingestion of a repository
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server  # type: ignore[import-untyped]
from mcp.server.models import InitializationOptions  # type: ignore[import-untyped]
from mcp.types import (  # type: ignore[import-untyped]
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

# ── Tool input schemas (JSON Schema) ────────────────────────────────────────

_TOOLS: list[Tool] = [
    Tool(
        name="search_code",
        description=(
            "Semantically search the indexed code base. "
            "Returns the most relevant functions, classes, and methods."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language or code search query"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
                "repo": {"type": "string", "description": "Filter to a specific repository"},
                "kind": {
                    "type": "string",
                    "enum": [
                        "function",
                        "method",
                        "class",
                        "module",
                        "variable",
                        "interface",
                        "type_alias",
                    ],
                    "description": "Filter by symbol kind",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_symbol",
        description="Retrieve full metadata (signature, docstring, location) for a code symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "string",
                    "description": "Unique symbol ID: <repo>#<file_path>#<name>",
                }
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="find_usages",
        description="Find all symbols (callers / importers) that depend on the given symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string"},
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="get_dependencies",
        description="Return the transitive dependency graph of a symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string"},
                "depth": {"type": "integer", "default": 2, "description": "Max traversal depth"},
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="analyze_impact",
        description=(
            "Identify all symbols that would be affected if the given symbol changes. "
            "Useful for understanding the blast-radius of a refactor or bug fix."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string"},
                "depth": {"type": "integer", "default": 3},
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="get_related_docs",
        description=(
            "Return API endpoints, documentation pages, and task tickets "
            "that are mapped to the given code symbol."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string"},
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="recommend",
        description="Recommend related symbols using hybrid semantic + graph search.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["symbol_id"],
        },
    ),
    Tool(
        name="index_repository",
        description="Trigger ingestion / re-indexing of a Git repository.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Git remote URL"},
                "name": {"type": "string", "description": "Short name / slug for the repository"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["url", "name"],
        },
    ),
]


# ── MCP Server factory ────────────────────────────────────────────────────────


def create_mcp_server(retrieval: Any | None = None) -> Server:
    """
    Build and return a configured MCP Server instance.

    *retrieval* should be a ``KnowledgeRetrieval`` instance; when *None*
    (e.g. in tests) all tool calls return a placeholder response.
    """
    server = Server("mysterial")

    @server.list_tools()
    async def list_tools(_req: ListToolsRequest) -> list[Tool]:  # type: ignore[misc]
        return _TOOLS

    @server.call_tool()
    async def call_tool(req: CallToolRequest) -> CallToolResult:  # type: ignore[misc]
        name = req.params.name
        args: dict[str, Any] = req.params.arguments or {}
        logger.debug("MCP tool call: %s %s", name, args)

        if retrieval is None:
            return _text_result({"error": "Retrieval service not available"})

        try:
            result = await _dispatch(name, args, retrieval)
        except Exception as exc:
            logger.exception("Error in MCP tool %s", name)
            return _text_result({"error": str(exc)})

        return _text_result(result)

    return server


async def _dispatch(name: str, args: dict[str, Any], retrieval: Any) -> Any:
    """Route a tool call to the appropriate retrieval method."""
    if name == "search_code":
        return retrieval.search_code(
            query=args["query"],
            limit=args.get("limit", 10),
            repo_filter=args.get("repo"),
            kind_filter=args.get("kind"),
        )
    if name == "get_symbol":
        return retrieval.get_symbol(args["symbol_id"])
    if name == "find_usages":
        return retrieval.find_usages(args["symbol_id"])
    if name == "get_dependencies":
        return retrieval.get_dependencies(
            args["symbol_id"], depth=args.get("depth", 2)
        )
    if name == "analyze_impact":
        return retrieval.analyze_impact(
            args["symbol_id"], depth=args.get("depth", 3)
        )
    if name == "get_related_docs":
        return retrieval.get_related_knowledge(args["symbol_id"])
    if name == "recommend":
        return retrieval.recommend(args["symbol_id"], limit=args.get("limit", 5))
    if name == "index_repository":
        # Trigger background indexing; return immediately
        asyncio.create_task(_background_index(args))
        return {"status": "indexing_started", "repo": args["name"]}
    return {"error": f"Unknown tool: {name}"}


async def _background_index(args: dict[str, Any]) -> None:
    """Run repository indexing in the background (best-effort)."""
    try:
        from mysterial.ingestion.repo_scanner import RepoScanner
        from mysterial.models.code import Repository

        repo = Repository(
            name=args["name"],
            url=args["url"],
            branch=args.get("branch", "main"),
        )
        scanner = RepoScanner()
        for _file in scanner.register_and_scan(repo):
            pass  # Full pipeline would process each file here
        logger.info("Background indexing complete for %s", args["name"])
    except Exception as exc:
        logger.exception("Background indexing failed for %s: %s", args.get("name"), exc)


def _text_result(data: Any) -> CallToolResult:
    """Wrap a Python value as a JSON TextContent CallToolResult."""
    text = json.dumps(data, default=str, indent=2)
    return CallToolResult(content=[TextContent(type="text", text=text)])


# ── Entry-points ──────────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP gateway via stdio (for Cursor / Claude Code)."""
    import argparse

    parser = argparse.ArgumentParser(description="Mysterial MCP Gateway")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="SSE host")
    parser.add_argument("--port", type=int, default=8001, help="SSE port")
    args = parser.parse_args()

    from mysterial.config import settings
    from mysterial.processing.embedding_generator import EmbeddingGenerator
    from mysterial.storage.graph_store import GraphStore
    from mysterial.storage.vector_store import VectorStore
    from mysterial.query.retrieval import KnowledgeRetrieval

    graph = GraphStore()
    vectors = VectorStore()
    embeddings = EmbeddingGenerator()
    graph.connect()
    vectors.connect()
    retrieval = KnowledgeRetrieval(graph=graph, vectors=vectors, embeddings=embeddings)

    server = create_mcp_server(retrieval)

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server  # type: ignore[import-untyped]

        async def _run_stdio() -> None:
            async with stdio_server() as (read_stream, write_stream):
                init_options = server.create_initialization_options()
                await server.run(read_stream, write_stream, init_options)

        asyncio.run(_run_stdio())
    else:
        import uvicorn
        from mcp.server.sse import SseServerTransport  # type: ignore[import-untyped]
        from starlette.applications import Starlette  # type: ignore[import-untyped]
        from starlette.routing import Mount, Route  # type: ignore[import-untyped]

        sse = SseServerTransport("/messages")

        async def handle_sse(request: Any) -> Any:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages", app=sse.handle_post_message),
            ]
        )
        uvicorn.run(starlette_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
