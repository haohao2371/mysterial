"""AST extractor – turns raw Tree-sitter node dicts into typed Symbol objects."""

from __future__ import annotations

import re
from typing import Any

from mysterial.models.code import Language, Symbol, SymbolKind

# Map tree-sitter node type → SymbolKind
_NODE_TYPE_TO_KIND: dict[str, SymbolKind] = {
    "function_definition": SymbolKind.FUNCTION,
    "async_function_definition": SymbolKind.FUNCTION,
    "function_declaration": SymbolKind.FUNCTION,
    "function_expression": SymbolKind.FUNCTION,
    "arrow_function": SymbolKind.FUNCTION,
    "class_definition": SymbolKind.CLASS,
    "class_declaration": SymbolKind.CLASS,
    "method_definition": SymbolKind.METHOD,
    "decorated_definition": SymbolKind.FUNCTION,
    "export_statement": SymbolKind.FUNCTION,
    "interface_declaration": SymbolKind.INTERFACE,
    "type_alias_declaration": SymbolKind.TYPE_ALIAS,
}


class ASTExtractor:
    """Convert raw node dicts (from TreeSitterParser) into Symbol model instances."""

    def extract(
        self,
        nodes: list[dict[str, Any]],
        language: Language,
        repo: str,
        file_path: str,
        source: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        for node in nodes:
            kind = _NODE_TYPE_TO_KIND.get(node["type"], SymbolKind.FUNCTION)
            name = node.get("name") or "<anonymous>"
            docstring = _extract_docstring(node.get("text", ""), language)
            signature = _extract_signature(node.get("text", ""), language)
            symbol = Symbol(
                id=Symbol.make_id(repo, file_path, name),
                name=name,
                qualified_name=f"{file_path}::{name}",
                kind=kind,
                language=language,
                repo=repo,
                file_path=file_path,
                line_start=node["start_line"],
                line_end=node["end_line"],
                docstring=docstring,
                signature=signature,
                body=node.get("text"),
            )
            symbols.append(symbol)
        return symbols


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_docstring(text: str, language: Language) -> str | None:
    """Extract the first docstring / JSDoc comment from raw symbol text."""
    if language == Language.PYTHON:
        # Triple-quoted string immediately after `def` / `class` header
        match = re.search(r'"""(.*?)"""', text, re.DOTALL)
        if not match:
            match = re.search(r"'''(.*?)'''", text, re.DOTALL)
        if match:
            return match.group(1).strip()
    else:
        # JSDoc: /** … */
        match = re.search(r"/\*\*(.*?)\*/", text, re.DOTALL)
        if match:
            # Strip leading * from each line
            raw = match.group(1)
            lines = [line.strip().lstrip("*").strip() for line in raw.splitlines()]
            return " ".join(filter(None, lines))
    return None


def _extract_signature(text: str, language: Language) -> str | None:
    """Extract the function/class signature (first line without body)."""
    if not text:
        return None
    first_line = text.splitlines()[0].strip()
    if language == Language.PYTHON:
        # Everything up to the colon
        colon_idx = first_line.rfind(":")
        if colon_idx != -1:
            return first_line[: colon_idx + 1]
    else:
        # JS/TS: up to the opening brace
        brace_idx = first_line.rfind("{")
        if brace_idx != -1:
            return first_line[:brace_idx].strip()
    return first_line
