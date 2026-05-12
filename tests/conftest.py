"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mysterial.models.code import Language, Symbol, SymbolKind
from mysterial.models.knowledge import APIEndpoint, DocPage


@pytest.fixture()
def sample_python_source() -> str:
    return '''\
def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"


class Calculator:
    """A simple calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
'''


@pytest.fixture()
def sample_symbol() -> Symbol:
    return Symbol(
        id="repo#src/foo.py#greet",
        name="greet",
        qualified_name="src/foo.py::greet",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        repo="repo",
        file_path="src/foo.py",
        line_start=1,
        line_end=3,
        docstring="Return a greeting string.",
        signature="def greet(name: str) -> str:",
        body='def greet(name: str) -> str:\n    """Return a greeting string."""\n    return f"Hello, {name}!"\n',
    )


@pytest.fixture()
def sample_endpoint() -> APIEndpoint:
    return APIEndpoint(
        id="myapi#GET#/users/{id}",
        spec_id="myapi",
        method="GET",
        path="/users/{id}",
        summary="Get user by ID",
        tags=["users"],
    )


@pytest.fixture()
def sample_doc_page() -> DocPage:
    return DocPage(
        id="confluence#123",
        source="confluence",
        title="User Service Documentation",
        url="https://wiki.example.com/user-service",
        content="The user service provides CRUD operations for user resources. "
        "The greet function returns a greeting for the given user.",
    )


@pytest.fixture()
def mock_graph_store() -> MagicMock:
    from mysterial.storage.graph_store import GraphStore

    mock = MagicMock(spec=GraphStore)
    mock.get_symbol.return_value = {
        "id": "repo#src/foo.py#greet",
        "name": "greet",
        "kind": "function",
        "language": "python",
        "repo": "repo",
        "file_path": "src/foo.py",
        "line_start": 1,
        "line_end": 3,
        "docstring": "Return a greeting string.",
        "signature": "def greet(name: str) -> str:",
    }
    mock.find_usages.return_value = []
    mock.get_dependencies.return_value = []
    mock.impact_analysis.return_value = []
    mock.get_related_knowledge.return_value = {"endpoints": [], "docs": [], "tasks": []}
    return mock


@pytest.fixture()
def mock_vector_store() -> MagicMock:
    from mysterial.storage.vector_store import VectorStore

    mock = MagicMock(spec=VectorStore)
    mock.search.return_value = [
        {
            "symbol_id": "repo#src/foo.py#greet",
            "name": "greet",
            "kind": "function",
            "language": "python",
            "repo": "repo",
            "file_path": "src/foo.py",
            "line_start": 1,
            "line_end": 3,
            "score": 0.92,
        }
    ]
    return mock


@pytest.fixture()
def mock_embedding_generator() -> MagicMock:
    from mysterial.processing.embedding_generator import EmbeddingGenerator

    mock = MagicMock(spec=EmbeddingGenerator)
    mock.embed.return_value = [0.1] * 384
    mock.embed_batch.return_value = [[0.1] * 384]
    mock.build_symbol_text.return_value = "greet | def greet(name: str) -> str: | Return a greeting string."
    return mock
