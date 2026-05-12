"""Tree-sitter based parser – converts source text into a list of raw AST node dicts."""

from __future__ import annotations

import logging
from typing import Any

from mysterial.models.code import Language

logger = logging.getLogger(__name__)


def _load_language(lang: Language) -> Any:
    """Lazily import the tree-sitter language binding."""
    if lang == Language.PYTHON:
        import tree_sitter_python as ts_lang  # type: ignore[import-untyped]

        return ts_lang.language()
    if lang in (Language.JAVASCRIPT, Language.TYPESCRIPT):
        import tree_sitter_javascript as ts_lang  # type: ignore[import-untyped]

        return ts_lang.language()
    raise ValueError(f"Unsupported language for tree-sitter: {lang}")


# Cache parsed Language objects so we don't reload on every call
_language_cache: dict[Language, Any] = {}
_parser_cache: dict[Language, Any] = {}


def _get_parser(lang: Language) -> Any:
    if lang not in _parser_cache:
        from tree_sitter import Language as TSLanguage, Parser  # type: ignore[import-untyped]

        ts_language = TSLanguage(_load_language(lang))
        _language_cache[lang] = ts_language
        parser = Parser(ts_language)
        _parser_cache[lang] = parser
    return _parser_cache[lang]


class TreeSitterParser:
    """Parse source code into a list of node-info dicts using Tree-sitter."""

    # Node types we care about per language
    _INTERESTING_TYPES: dict[Language, set[str]] = {
        Language.PYTHON: {
            "function_definition",
            "async_function_definition",
            "class_definition",
            "decorated_definition",
        },
        Language.JAVASCRIPT: {
            "function_declaration",
            "function_expression",
            "arrow_function",
            "class_declaration",
            "method_definition",
            "export_statement",
        },
        Language.TYPESCRIPT: {
            "function_declaration",
            "function_expression",
            "arrow_function",
            "class_declaration",
            "method_definition",
            "interface_declaration",
            "type_alias_declaration",
        },
    }

    def parse(self, source: str | bytes, language: Language) -> list[dict[str, Any]]:
        """
        Parse *source* and return a flat list of interesting AST nodes.

        Each entry is a dict with keys:
          type, name, start_line, end_line, start_byte, end_byte, text
        """
        if isinstance(source, str):
            source_bytes = source.encode("utf-8")
        else:
            source_bytes = source

        try:
            parser = _get_parser(language)
        except Exception as exc:
            logger.warning("Parser unavailable for %s: %s", language, exc)
            return []

        tree = parser.parse(source_bytes)
        interesting = self._INTERESTING_TYPES.get(language, set())
        nodes: list[dict[str, Any]] = []
        self._walk(tree.root_node, source_bytes, interesting, nodes)
        return nodes

    # ── Internal helpers ────────────────────────────────────────────────

    def _walk(
        self,
        node: Any,
        source: bytes,
        interesting: set[str],
        results: list[dict[str, Any]],
    ) -> None:
        if node.type in interesting:
            name = self._extract_name(node, source)
            results.append(
                {
                    "type": node.type,
                    "name": name,
                    "start_line": node.start_point[0] + 1,  # 1-indexed
                    "end_line": node.end_point[0] + 1,
                    "start_byte": node.start_byte,
                    "end_byte": node.end_byte,
                    "text": source[node.start_byte : node.end_byte].decode(
                        "utf-8", errors="replace"
                    ),
                }
            )
        for child in node.children:
            self._walk(child, source, interesting, results)

    @staticmethod
    def _extract_name(node: Any, source: bytes) -> str:
        """Best-effort extraction of a symbol name from an AST node."""
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte : child.end_byte].decode(
                    "utf-8", errors="replace"
                )
        # Fallback: return node type
        return node.type
