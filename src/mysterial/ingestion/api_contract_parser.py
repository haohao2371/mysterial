"""API contract parser – extracts endpoints from OpenAPI (v2/v3) and GraphQL schemas."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from mysterial.models.knowledge import APIEndpoint

logger = logging.getLogger(__name__)


class OpenAPIParser:
    """Parse an OpenAPI 2 (Swagger) or OpenAPI 3 spec into APIEndpoint objects."""

    def parse_file(self, path: str | Path) -> list[APIEndpoint]:
        """Load YAML or JSON spec from *path* and return all endpoints."""
        data = self._load(Path(path))
        return self.parse_dict(str(path), data)

    def parse_dict(self, spec_id: str, spec: dict[str, Any]) -> list[APIEndpoint]:
        """Parse a spec dict that has already been loaded into memory."""
        endpoints: list[APIEndpoint] = []
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "options",
                    "head",
                }:
                    continue
                if not isinstance(operation, dict):
                    continue
                endpoint = APIEndpoint(
                    id=f"{spec_id}#{method.upper()}#{path}",
                    spec_id=spec_id,
                    method=method.upper(),
                    path=path,
                    summary=operation.get("summary"),
                    description=operation.get("description"),
                    request_schema=self._extract_request_schema(operation, spec),
                    response_schema=self._extract_response_schema(operation, spec),
                    tags=operation.get("tags", []),
                )
                endpoints.append(endpoint)
        return endpoints

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)  # type: ignore[return-value]
        return json.loads(text)  # type: ignore[return-value]

    @staticmethod
    def _extract_request_schema(
        operation: dict[str, Any], spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        # OpenAPI 3.x requestBody
        request_body = operation.get("requestBody", {})
        if request_body:
            content = request_body.get("content", {})
            for mime, media in content.items():
                schema = media.get("schema")
                if schema:
                    return {"mime": mime, "schema": schema}
        # OpenAPI 2 body parameter
        for param in operation.get("parameters", []):
            if isinstance(param, dict) and param.get("in") == "body":
                return {"schema": param.get("schema")}
        return None

    @staticmethod
    def _extract_response_schema(
        operation: dict[str, Any], spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        responses = operation.get("responses", {})
        for status_code in ("200", "201", "default"):
            response = responses.get(status_code, {})
            if not response:
                continue
            # OpenAPI 3.x
            content = response.get("content", {})
            for mime, media in content.items():
                schema = media.get("schema")
                if schema:
                    return {"status_code": status_code, "mime": mime, "schema": schema}
            # OpenAPI 2
            schema = response.get("schema")
            if schema:
                return {"status_code": status_code, "schema": schema}
        return None


class GraphQLSchemaParser:
    """Extract operation names and types from a GraphQL SDL schema string."""

    def parse(self, spec_id: str, sdl: str) -> list[APIEndpoint]:
        """
        Parse a GraphQL SDL and return an APIEndpoint per root operation
        (Query field, Mutation field, Subscription field).
        """
        endpoints: list[APIEndpoint] = []
        current_type: str | None = None
        operation_type_map = {
            "Query": "QUERY",
            "Mutation": "MUTATION",
            "Subscription": "SUBSCRIPTION",
        }
        for line in sdl.splitlines():
            stripped = line.strip()
            # Detect type block opening
            for gql_type, method in operation_type_map.items():
                if stripped.startswith(f"type {gql_type}"):
                    current_type = method
                    break
            else:
                if stripped.startswith("type ") or stripped == "}":
                    current_type = None

            if current_type and ":" in stripped and not stripped.startswith("#"):
                # e.g.  searchCode(query: String!): [Symbol]
                field_name = stripped.split("(")[0].split(":")[0].strip()
                if field_name and field_name not in {"{", "}"}:
                    endpoints.append(
                        APIEndpoint(
                            id=f"{spec_id}#{current_type}#{field_name}",
                            spec_id=spec_id,
                            method=current_type,
                            path=field_name,
                            summary=f"GraphQL {current_type}: {field_name}",
                        )
                    )
        return endpoints
