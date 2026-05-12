"""Models for knowledge artifacts: API contracts, docs, tasks."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class APIEndpoint(BaseModel):
    """An API endpoint parsed from an OpenAPI / GraphQL schema."""

    id: str = Field(description="<spec_id>#<method>#<path>")
    spec_id: str
    method: str  # GET | POST | PUT | DELETE | PATCH | QUERY | MUTATION | SUBSCRIPTION
    path: str
    summary: Optional[str] = None
    description: Optional[str] = None
    request_schema: Optional[dict[str, Any]] = None
    response_schema: Optional[dict[str, Any]] = None
    tags: list[str] = Field(default_factory=list)


class DocPage(BaseModel):
    """A documentation page from Confluence or another docs system."""

    id: str
    source: str = Field(description="confluence | markdown | notion")
    title: str
    url: str
    content: str
    space: Optional[str] = None
    parent_id: Optional[str] = None
    embedding: Optional[list[float]] = Field(default=None, exclude=True)


class Task(BaseModel):
    """A work item (Jira issue, GitHub issue, etc.)."""

    id: str
    source: str = Field(description="jira | github | linear")
    key: str  # e.g. PROJ-123
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    labels: list[str] = Field(default_factory=list)


class MappingKind(str, Enum):
    CODE_TO_API = "code_to_api"
    CODE_TO_DOC = "code_to_doc"
    CODE_TO_TASK = "code_to_task"
    API_TO_DOC = "api_to_doc"
    API_TO_TASK = "api_to_task"


class KnowledgeMapping(BaseModel):
    """A discovered or LLM-validated mapping between two knowledge entities."""

    from_id: str
    to_id: str
    kind: MappingKind
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: str = Field(description="auto | llm | manual")
