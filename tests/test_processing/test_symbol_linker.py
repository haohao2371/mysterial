"""Tests for SymbolLinker."""

from __future__ import annotations

import pytest

from mysterial.models.code import Language, Symbol, SymbolKind
from mysterial.models.knowledge import APIEndpoint, DocPage, MappingKind
from mysterial.processing.symbol_linker import SymbolLinker


def _make_symbol(name: str, body: str = "") -> Symbol:
    return Symbol(
        id=f"repo#src/foo.py#{name}",
        name=name,
        qualified_name=f"src/foo.py::{name}",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        repo="repo",
        file_path="src/foo.py",
        line_start=1,
        line_end=5,
        body=body,
    )


class TestSymbolLinkerCallDependencies:
    def test_detects_call(self) -> None:
        linker = SymbolLinker()
        caller = _make_symbol("do_work", body="def do_work():\n    helper()\n")
        helper = _make_symbol("helper")
        deps = linker.extract_call_dependencies(caller, [caller, helper])
        assert len(deps) == 1
        assert deps[0].from_symbol_id == caller.id
        assert deps[0].to_symbol_id == helper.id
        assert deps[0].kind == "calls"

    def test_no_self_dependency(self) -> None:
        linker = SymbolLinker()
        sym = _make_symbol("foo", body="def foo():\n    foo()\n")
        deps = linker.extract_call_dependencies(sym, [sym])
        assert deps == []

    def test_returns_empty_when_no_body(self) -> None:
        linker = SymbolLinker()
        sym = _make_symbol("bar")
        deps = linker.extract_call_dependencies(sym, [sym])
        assert deps == []

    def test_skips_short_names(self) -> None:
        linker = SymbolLinker()
        caller = _make_symbol("main", body="def main():\n    fn()\n")
        short = _make_symbol("fn")
        deps = linker.extract_call_dependencies(caller, [caller, short])
        # "fn" is 2 chars – should be skipped
        assert deps == []


class TestSymbolLinkerMapToEndpoints:
    def test_maps_by_path_segment(self) -> None:
        linker = SymbolLinker()
        # "get_users" contains both "get" (HTTP method) and "users" (path segment)
        sym = _make_symbol("get_users")
        endpoint = APIEndpoint(
            id="api#GET#/users",
            spec_id="api",
            method="GET",
            path="/users",
            summary="List users",
        )
        mappings = linker.map_symbols_to_endpoints([sym], [endpoint])
        assert len(mappings) == 1
        assert mappings[0].from_id == sym.id
        assert mappings[0].to_id == endpoint.id
        assert mappings[0].kind == MappingKind.CODE_TO_API

    def test_no_mapping_when_unrelated(self) -> None:
        linker = SymbolLinker()
        sym = _make_symbol("process_payment")
        endpoint = APIEndpoint(
            id="api#POST#/orders",
            spec_id="api",
            method="POST",
            path="/orders",
            summary="Create order",
        )
        mappings = linker.map_symbols_to_endpoints([sym], [endpoint])
        # No common tokens, should not map
        assert all(m.confidence < 0.4 for m in mappings) or mappings == []


class TestSymbolLinkerMapToDocs:
    def test_maps_when_name_mentioned_twice(self) -> None:
        linker = SymbolLinker()
        sym = _make_symbol("greet")
        page = DocPage(
            id="doc#1",
            source="confluence",
            title="Greeting service",
            url="http://example.com",
            content="The greet function is used in the greet service to produce messages.",
        )
        mappings = linker.map_symbols_to_docs([sym], [page])
        assert len(mappings) == 1
        assert mappings[0].kind == MappingKind.CODE_TO_DOC

    def test_no_mapping_when_name_not_present(self) -> None:
        linker = SymbolLinker()
        sym = _make_symbol("calculate_taxes")
        page = DocPage(
            id="doc#2",
            source="confluence",
            title="Deployment guide",
            url="http://example.com",
            content="This document describes the deployment process.",
        )
        mappings = linker.map_symbols_to_docs([sym], [page])
        assert mappings == []
