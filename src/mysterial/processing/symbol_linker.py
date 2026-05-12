"""Symbol linker – resolves cross-repository and code↔API↔docs relationships."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from mysterial.models.code import Dependency
from mysterial.models.knowledge import APIEndpoint, DocPage, KnowledgeMapping, MappingKind

if TYPE_CHECKING:
    from mysterial.models.code import Symbol

logger = logging.getLogger(__name__)


class SymbolLinker:
    """
    Produce Dependency and KnowledgeMapping edges by analysing symbol texts
    and comparing them against API/doc contents.
    """

    # ── Code → Code dependencies ─────────────────────────────────────────

    def extract_call_dependencies(
        self, symbol: "Symbol", all_symbols: list["Symbol"]
    ) -> list[Dependency]:
        """Detect call/import edges by looking for other symbol names inside symbol.body."""
        if not symbol.body:
            return []
        deps: list[Dependency] = []
        name_to_symbol = {s.name: s for s in all_symbols if s.id != symbol.id}
        for name, target in name_to_symbol.items():
            # Avoid trivial single-char name matches
            if len(name) < 3:
                continue
            pattern = r"\b" + re.escape(name) + r"\b"
            if re.search(pattern, symbol.body):
                deps.append(
                    Dependency(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        kind="calls",
                    )
                )
        return deps

    def extract_import_dependencies(
        self, symbol: "Symbol", all_symbols: list["Symbol"]
    ) -> list[Dependency]:
        """Detect import-style edges (Python import / JS require / import)."""
        if not symbol.body:
            return []
        deps: list[Dependency] = []
        # Collect imported names from the symbol body
        imported_names: set[str] = set()

        # Python: `from x import y` / `import x`
        for m in re.finditer(r"(?:from\s+\S+\s+)?import\s+([\w, ]+)", symbol.body):
            for name in m.group(1).split(","):
                imported_names.add(name.strip())

        # JS/TS: `import { x } from 'y'` / `const x = require('y')`
        for m in re.finditer(r"import\s*\{([^}]+)\}", symbol.body):
            for name in m.group(1).split(","):
                imported_names.add(name.strip())

        name_to_symbol = {s.name: s for s in all_symbols if s.id != symbol.id}
        for name in imported_names:
            target = name_to_symbol.get(name)
            if target:
                deps.append(
                    Dependency(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        kind="imports",
                    )
                )
        return deps

    # ── Code ↔ API mappings ──────────────────────────────────────────────

    def map_symbols_to_endpoints(
        self,
        symbols: list["Symbol"],
        endpoints: list[APIEndpoint],
    ) -> list[KnowledgeMapping]:
        """
        Heuristically link symbols to API endpoints by matching path segments
        and method names.
        """
        mappings: list[KnowledgeMapping] = []
        for endpoint in endpoints:
            path_parts = {p.lower().strip("{}") for p in endpoint.path.split("/") if p}
            for symbol in symbols:
                score = self._symbol_endpoint_score(symbol, endpoint, path_parts)
                if score > 0.4:
                    mappings.append(
                        KnowledgeMapping(
                            from_id=symbol.id,
                            to_id=endpoint.id,
                            kind=MappingKind.CODE_TO_API,
                            confidence=min(score, 1.0),
                            source="auto",
                        )
                    )
        return mappings

    # ── Code ↔ Docs mappings ─────────────────────────────────────────────

    def map_symbols_to_docs(
        self,
        symbols: list["Symbol"],
        pages: list[DocPage],
    ) -> list[KnowledgeMapping]:
        """Link symbols to doc pages where the symbol name appears prominently."""
        mappings: list[KnowledgeMapping] = []
        for page in pages:
            page_text_lower = page.title.lower() + " " + page.content.lower()
            for symbol in symbols:
                name_lower = symbol.name.lower()
                if len(name_lower) < 4:
                    continue
                count = page_text_lower.count(name_lower)
                if count >= 2:
                    confidence = min(count / 10.0, 1.0)
                    mappings.append(
                        KnowledgeMapping(
                            from_id=symbol.id,
                            to_id=page.id,
                            kind=MappingKind.CODE_TO_DOC,
                            confidence=confidence,
                            source="auto",
                        )
                    )
        return mappings

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _symbol_endpoint_score(
        symbol: "Symbol", endpoint: APIEndpoint, path_parts: set[str]
    ) -> float:
        """Return a confidence score [0, 1] that symbol implements endpoint."""
        name_lower = symbol.name.lower()
        score = 0.0

        # HTTP method in symbol name
        method_lower = endpoint.method.lower()
        if method_lower in name_lower:
            score += 0.3

        # Path segments in symbol name
        matches = sum(1 for part in path_parts if part in name_lower)
        if path_parts:
            score += 0.5 * matches / len(path_parts)

        # Summary keywords
        if endpoint.summary:
            for word in endpoint.summary.lower().split():
                if len(word) > 4 and word in name_lower:
                    score += 0.1
                    break

        return score
