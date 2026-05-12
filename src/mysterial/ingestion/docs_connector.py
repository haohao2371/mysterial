"""Docs connector – retrieves pages from Confluence and issues from Jira."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from mysterial.models.knowledge import DocPage, Task

logger = logging.getLogger(__name__)


class ConfluenceConnector:
    """Fetch pages from an Atlassian Confluence instance via the REST API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, api_token)
        self._verify_ssl = verify_ssl

    # ── Public API ──────────────────────────────────────────────────────

    def fetch_pages(
        self,
        space_key: str,
        limit: int = 100,
        start: int = 0,
    ) -> list[DocPage]:
        """Fetch all pages in a Confluence space."""
        pages: list[DocPage] = []
        while True:
            data = self._get(
                "/rest/api/content",
                params={
                    "type": "page",
                    "spaceKey": space_key,
                    "expand": "body.storage,metadata.labels",
                    "limit": limit,
                    "start": start,
                },
            )
            for result in data.get("results", []):
                pages.append(self._to_doc_page(result, space_key))
            if data.get("_links", {}).get("next"):
                start += limit
            else:
                break
        return pages

    # ── Internal helpers ────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        resp = httpx.get(url, auth=self._auth, params=params, verify=self._verify_ssl)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    def _to_doc_page(result: dict[str, Any], space: str) -> DocPage:
        body = result.get("body", {}).get("storage", {}).get("value", "")
        return DocPage(
            id=f"confluence#{result['id']}",
            source="confluence",
            title=result["title"],
            url=result.get("_links", {}).get("self", ""),
            content=body,
            space=space,
            parent_id=result.get("ancestors", [{}])[-1].get("id"),
        )


class JiraConnector:
    """Fetch issues from a Jira Cloud instance via the REST API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, api_token)
        self._verify_ssl = verify_ssl

    # ── Public API ──────────────────────────────────────────────────────

    def fetch_issues(
        self,
        jql: str = "ORDER BY created DESC",
        max_results: int = 100,
    ) -> list[Task]:
        """Fetch Jira issues matching a JQL query."""
        tasks: list[Task] = []
        start_at = 0
        while True:
            data = self._post(
                "/rest/api/3/search",
                json={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": max_results,
                    "fields": ["summary", "description", "status", "assignee", "labels"],
                },
            )
            for issue in data.get("issues", []):
                tasks.append(self._to_task(issue))
            total = data.get("total", 0)
            start_at += len(data.get("issues", []))
            if start_at >= total:
                break
        return tasks

    # ── Internal helpers ────────────────────────────────────────────────

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        resp = httpx.post(url, auth=self._auth, json=json, verify=self._verify_ssl)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    def _to_task(issue: dict[str, Any]) -> Task:
        fields = issue.get("fields", {})
        description_obj = fields.get("description") or {}
        # Jira description is ADF (Atlassian Document Format); extract plain text
        description = _extract_adf_text(description_obj) if description_obj else None
        return Task(
            id=f"jira#{issue['id']}",
            source="jira",
            key=issue["key"],
            title=fields.get("summary", ""),
            description=description,
            status=fields.get("status", {}).get("name"),
            assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            labels=fields.get("labels", []),
        )


def _extract_adf_text(adf_node: dict[str, Any]) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if adf_node.get("type") == "text":
        return adf_node.get("text", "")
    parts: list[str] = []
    for child in adf_node.get("content", []):
        parts.append(_extract_adf_text(child))
    return " ".join(filter(None, parts))
