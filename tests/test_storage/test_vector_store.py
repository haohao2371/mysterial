"""Tests for VectorStore (unit tests using mocked Qdrant client)."""

from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from mysterial.models.code import Language, Symbol, SymbolKind
from mysterial.storage.vector_store import VectorStore


def _make_qdrant_mock() -> MagicMock:
    """Return a mock that satisfies `from qdrant_client.models import PointStruct …`."""
    mock_models = MagicMock()
    mock_qdrant = MagicMock()
    mock_qdrant.models = mock_models
    # PointStruct(id=..., vector=..., payload=...) returns something with .id attribute
    mock_models.PointStruct.side_effect = lambda id, vector, payload: MagicMock(id=id)
    # Filter / FieldCondition / MatchValue just return MagicMock instances
    return mock_qdrant


def _make_vector_store() -> tuple[VectorStore, MagicMock]:
    store = VectorStore(
        host="localhost", port=6333, collection="test", embedding_dim=4
    )
    mock_client = MagicMock()
    store._client = mock_client
    return store, mock_client


@pytest.fixture(autouse=True)
def patch_qdrant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure qdrant_client is available as a mock throughout these tests."""
    mock_qdrant_pkg = _make_qdrant_mock()
    monkeypatch.setitem(sys.modules, "qdrant_client", mock_qdrant_pkg)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", mock_qdrant_pkg.models)


class TestVectorStoreUpsert:
    def test_upsert_symbol_calls_client(self) -> None:
        store, client = _make_vector_store()
        sym = Symbol(
            id="repo#src/foo.py#greet",
            name="greet",
            qualified_name="src/foo.py::greet",
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            repo="repo",
            file_path="src/foo.py",
            line_start=1,
            line_end=3,
        )
        embedding = [0.1, 0.2, 0.3, 0.4]
        store.upsert_symbol(sym, embedding)
        assert client.upsert.called

    def test_upsert_symbol_uses_deterministic_id(self) -> None:
        store, client = _make_vector_store()
        sym = Symbol(
            id="repo#src/foo.py#greet",
            name="greet",
            qualified_name="src/foo.py::greet",
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            repo="repo",
            file_path="src/foo.py",
            line_start=1,
            line_end=3,
        )
        embedding = [0.1, 0.2, 0.3, 0.4]
        store.upsert_symbol(sym, embedding)
        store.upsert_symbol(sym, embedding)
        # The same symbol ID should always produce the same UUID point ID
        expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, sym.id))
        call1_points = client.upsert.call_args_list[0][1]["points"]
        call2_points = client.upsert.call_args_list[1][1]["points"]
        # Both calls should have passed points with the same id
        assert call1_points[0].id == call2_points[0].id

    def test_raises_without_connect(self) -> None:
        store = VectorStore()
        sym = Symbol(
            id="x",
            name="x",
            qualified_name="x",
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            repo="r",
            file_path="f.py",
            line_start=1,
            line_end=1,
        )
        with pytest.raises(RuntimeError, match="connect"):
            store.upsert_symbol(sym, [0.1])


class TestVectorStoreSearch:
    def test_search_returns_hits(self) -> None:
        store, client = _make_vector_store()
        mock_hit = MagicMock()
        mock_hit.payload = {"symbol_id": "x", "name": "foo"}
        mock_hit.score = 0.9
        client.search.return_value = [mock_hit]

        results = store.search([0.1, 0.2, 0.3, 0.4], limit=5)
        assert len(results) == 1
        assert results[0]["score"] == 0.9

    def test_search_with_repo_filter(self) -> None:
        store, client = _make_vector_store()
        client.search.return_value = []
        store.search([0.1] * 4, limit=5, repo_filter="myrepo")
        # Verify filter was passed as a non-None value
        call_kwargs = client.search.call_args[1]
        assert call_kwargs["query_filter"] is not None

    def test_search_without_filter(self) -> None:
        store, client = _make_vector_store()
        client.search.return_value = []
        store.search([0.1] * 4, limit=5)
        call_kwargs = client.search.call_args[1]
        assert call_kwargs["query_filter"] is None

