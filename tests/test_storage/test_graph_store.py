"""Tests for GraphStore (unit tests using mocked neo4j driver)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mysterial.models.code import Dependency, Language, Repository, Symbol, SymbolKind
from mysterial.storage.graph_store import GraphStore


def _make_graph_store() -> tuple[GraphStore, MagicMock]:
    """Return a GraphStore with a mocked neo4j driver."""
    store = GraphStore(uri="bolt://localhost:7687", user="neo4j", password="test")
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver.session.return_value.__exit__.return_value = False
    store._driver = mock_driver
    return store, mock_session


class TestGraphStoreUpserts:
    def test_upsert_symbol_runs_query(self) -> None:
        store, session = _make_graph_store()
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
        store.upsert_symbol(sym)
        assert session.run.called

    def test_upsert_repository_runs_query(self) -> None:
        store, session = _make_graph_store()
        repo = Repository(name="myrepo", url="https://github.com/org/myrepo")
        store.upsert_repository(repo)
        assert session.run.called

    def test_upsert_dependency_runs_query(self) -> None:
        store, session = _make_graph_store()
        dep = Dependency(
            from_symbol_id="repo#a.py#foo",
            to_symbol_id="repo#b.py#bar",
            kind="calls",
        )
        store.upsert_dependency(dep)
        assert session.run.called


class TestGraphStoreReads:
    def test_get_symbol_returns_dict(self) -> None:
        store, session = _make_graph_store()
        mock_record = MagicMock()
        mock_record.__getitem__.return_value = {"id": "x", "name": "foo"}
        session.run.return_value.single.return_value = mock_record

        result = store.get_symbol("x")
        assert isinstance(result, dict)

    def test_get_symbol_returns_none_when_missing(self) -> None:
        store, session = _make_graph_store()
        session.run.return_value.single.return_value = None

        result = store.get_symbol("nonexistent")
        assert result is None

    def test_find_usages_returns_list(self) -> None:
        store, session = _make_graph_store()
        mock_row = MagicMock()
        mock_row.__getitem__.return_value = {"id": "caller#id", "name": "main"}
        session.run.return_value.__iter__ = lambda self: iter([mock_row])

        results = store.find_usages("some#symbol#id")
        assert isinstance(results, list)

    def test_raises_without_connect(self) -> None:
        store = GraphStore()
        # _driver is None – should raise RuntimeError
        with pytest.raises(RuntimeError, match="connect"):
            store.get_symbol("x")
