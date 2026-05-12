"""Pydantic models representing code-level entities extracted from repositories."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SymbolKind(str, Enum):
    """The syntactic kind of a code symbol."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENDPOINT = "endpoint"  # API route handler


class Language(str, Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


class Symbol(BaseModel):
    """A code symbol (function, class, method, …) extracted from source code."""

    id: str = Field(description="Unique identifier: <repo>#<file_path>#<name>")
    name: str
    qualified_name: str = Field(description="Fully-qualified name within the file")
    kind: SymbolKind
    language: Language
    repo: str = Field(description="Repository name / identifier")
    file_path: str = Field(description="Relative path within the repository")
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    signature: Optional[str] = None
    body: Optional[str] = None
    embedding: Optional[list[float]] = Field(default=None, exclude=True)

    @classmethod
    def make_id(cls, repo: str, file_path: str, name: str) -> str:
        return f"{repo}#{file_path}#{name}"


class FileRecord(BaseModel):
    """Metadata for a source file discovered during ingestion."""

    repo: str
    path: str = Field(description="Relative path within the repository")
    language: Language
    size_bytes: int
    content_hash: str


class Repository(BaseModel):
    """A registered repository entry."""

    name: str = Field(description="Short identifier / slug")
    url: str
    branch: str = Field(default="main")
    local_path: Optional[str] = None
    last_indexed: Optional[str] = None  # ISO-8601 datetime string


class Dependency(BaseModel):
    """An edge in the dependency graph between two symbols."""

    from_symbol_id: str
    to_symbol_id: str
    kind: str = Field(description="calls | imports | inherits | implements")
