# Mysterial – Internal AI Code Knowledge Platform

An internal AI-powered engineering knowledge platform that indexes repositories, extracts source code structure, maps code ↔ API ↔ docs ↔ tasks, and exposes MCP tools for AI IDE assistants.

---

## Architecture

```text
                ┌────────────────────────────┐
                │     External Sources        │
                │ Git Repos · Jira · OpenAPI  │
                │ Confluence · GraphQL SDL    │
                └─────────────┬──────────────┘
                              │
                              ▼
                ┌────────────────────────────┐
                │     Ingestion Layer         │
                │ RepoScanner                 │
                │ TreeSitterParser            │
                │ DocsConnector               │
                │ APIContractParser           │
                └─────────────┬──────────────┘
                              │
                              ▼
                ┌────────────────────────────┐
                │  Semantic Processing Layer  │
                │ ASTExtractor                │
                │ EmbeddingGenerator          │
                │ SymbolLinker                │
                └──────┬────────────┬────────┘
                       │            │
                       ▼            ▼
            ┌──────────────┐  ┌──────────────┐
            │  Neo4j Graph │  │ Qdrant Vector│
            │  Database    │  │ Database     │
            └──────┬───────┘  └──────┬───────┘
                   │                 │
                   └───────┬─────────┘
                           ▼
               ┌────────────────────────┐
               │  Knowledge Query       │
               │  GraphQL + Retrieval   │
               └──────────┬─────────────┘
                          ▼
               ┌────────────────────────┐
               │     MCP Gateway        │
               └──────────┬─────────────┘
                          ▼
         Cursor / VSCode Copilot / Claude Code
```

---

## Quick Start

### 1. Start infrastructure

```bash
docker-compose up -d neo4j qdrant
```

### 2. Install the package

```bash
pip install -e ".[dev]"
```

### 3. Configure

```bash
cp .env.example .env
# edit .env with your settings
```

### 4. Start the API server

```bash
uvicorn mysterial.api.app:app --reload
```

Open <http://localhost:8000/graphql> for the GraphQL playground.

### 5. Index a repository

```bash
curl -X POST http://localhost:8000/ingest/repository \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/your-org/your-repo", "name": "your-repo"}'
```

### 6. Connect from Cursor / Claude Code (MCP stdio)

Add to your MCP config:

```json
{
  "mcpServers": {
    "mysterial": {
      "command": "mysterial-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Or run as an SSE server (for remote IDE connections):

```bash
mysterial-mcp --transport sse --port 8001
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_code` | Semantic search across all indexed code |
| `get_symbol` | Retrieve metadata for a specific symbol |
| `find_usages` | Find callers / importers of a symbol |
| `get_dependencies` | Transitive dependency graph |
| `analyze_impact` | Blast-radius analysis for a change |
| `get_related_docs` | Linked API endpoints, docs, and tasks |
| `recommend` | Hybrid graph + vector recommendations |
| `index_repository` | Trigger ingestion of a new repository |

---

## GraphQL API

```graphql
query SearchCode {
  searchCode(query: "user authentication", limit: 5) {
    id name kind repo filePath lineStart docstring score
  }
}

query GetImpact {
  analyzeImpact(symbolId: "my-repo#src/auth.py#validate_token", depth: 3) {
    id name filePath
  }
}
```

---

## Project Structure

```
src/mysterial/
├── config.py              # Pydantic-settings configuration
├── models/
│   ├── code.py            # Symbol, Repository, FileRecord, Dependency
│   └── knowledge.py       # APIEndpoint, DocPage, Task, KnowledgeMapping
├── ingestion/
│   ├── repo_scanner.py    # Git clone + file discovery
│   ├── tree_sitter_parser.py  # AST node extraction
│   ├── docs_connector.py  # Confluence + Jira connectors
│   └── api_contract_parser.py  # OpenAPI / GraphQL SDL parser
├── processing/
│   ├── ast_extractor.py   # AST nodes → Symbol models
│   ├── embedding_generator.py  # sentence-transformers wrapper
│   └── symbol_linker.py   # Cross-repo + code↔API↔docs linking
├── storage/
│   ├── graph_store.py     # Neo4j driver wrapper
│   └── vector_store.py    # Qdrant wrapper
├── query/
│   ├── schema.py          # Strawberry GraphQL schema
│   └── retrieval.py       # Hybrid graph + vector retrieval facade
├── mcp/
│   └── gateway.py         # MCP server (stdio + SSE transports)
└── api/
    └── app.py             # FastAPI application
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests use mocks for all external services (Neo4j, Qdrant, sentence-transformers), so no running infrastructure is needed.

---

## Supported Languages

- Python (`.py`)
- JavaScript (`.js`, `.mjs`, `.cjs`)
- TypeScript (`.ts`, `.tsx`)
