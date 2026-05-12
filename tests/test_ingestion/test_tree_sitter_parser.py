"""Tests for the TreeSitterParser (with tree-sitter libraries available)."""

from __future__ import annotations

import pytest

from mysterial.models.code import Language

# Import is conditional because tree-sitter bindings may not be installed
try:
    from mysterial.ingestion.tree_sitter_parser import TreeSitterParser

    TS_AVAILABLE = True
except Exception:
    TS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not TS_AVAILABLE, reason="tree-sitter not installed")


@pytest.fixture()
def parser() -> "TreeSitterParser":
    return TreeSitterParser()


class TestTreeSitterParserPython:
    def test_parses_function_definition(self, parser: "TreeSitterParser") -> None:
        source = "def hello(name: str) -> str:\n    return f'Hello, {name}!'\n"
        nodes = parser.parse(source, Language.PYTHON)
        assert len(nodes) >= 1
        func = next((n for n in nodes if "function" in n["type"]), None)
        assert func is not None
        assert func["name"] == "hello"

    def test_parses_class_definition(self, parser: "TreeSitterParser") -> None:
        source = "class Foo:\n    pass\n"
        nodes = parser.parse(source, Language.PYTHON)
        classes = [n for n in nodes if n["type"] == "class_definition"]
        assert len(classes) == 1
        assert classes[0]["name"] == "Foo"

    def test_parses_multiple_symbols(
        self, parser: "TreeSitterParser", sample_python_source: str
    ) -> None:
        nodes = parser.parse(sample_python_source, Language.PYTHON)
        names = {n["name"] for n in nodes}
        # greet + Calculator + add + subtract should all appear
        assert "greet" in names
        assert "Calculator" in names

    def test_line_numbers_are_correct(self, parser: "TreeSitterParser") -> None:
        source = "x = 1\ndef foo():\n    pass\n"
        nodes = parser.parse(source, Language.PYTHON)
        func = next((n for n in nodes if n["name"] == "foo"), None)
        assert func is not None
        assert func["start_line"] == 2

    def test_returns_empty_for_empty_source(self, parser: "TreeSitterParser") -> None:
        nodes = parser.parse("", Language.PYTHON)
        assert nodes == []

    def test_handles_bytes_input(self, parser: "TreeSitterParser") -> None:
        source = b"def bar():\n    pass\n"
        nodes = parser.parse(source, Language.PYTHON)
        assert len(nodes) >= 1


class TestTreeSitterParserJavaScript:
    def test_parses_function_declaration(self, parser: "TreeSitterParser") -> None:
        source = "function add(a, b) { return a + b; }"
        nodes = parser.parse(source, Language.JAVASCRIPT)
        assert len(nodes) >= 1
        func = next((n for n in nodes if "function" in n["type"]), None)
        assert func is not None

    def test_parses_class_declaration(self, parser: "TreeSitterParser") -> None:
        source = "class MyClass { constructor() {} }"
        nodes = parser.parse(source, Language.JAVASCRIPT)
        classes = [n for n in nodes if n["type"] == "class_declaration"]
        assert len(classes) == 1


class TestTreeSitterParserUnknown:
    def test_returns_empty_for_unknown_language(
        self, parser: "TreeSitterParser"
    ) -> None:
        nodes = parser.parse("SELECT * FROM users;", Language.UNKNOWN)
        assert nodes == []
