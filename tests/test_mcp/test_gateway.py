"""Tests for the MCP gateway tool definitions and dispatch logic."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mysterial.mcp.gateway import _TOOLS, _dispatch, _text_result, create_mcp_server


class TestToolDefinitions:
    def test_all_required_tools_present(self) -> None:
        tool_names = {t.name for t in _TOOLS}
        required = {
            "search_code",
            "get_symbol",
            "find_usages",
            "get_dependencies",
            "analyze_impact",
            "get_related_docs",
            "recommend",
            "index_repository",
        }
        assert required.issubset(tool_names)

    def test_each_tool_has_description(self) -> None:
        for tool in _TOOLS:
            assert tool.description, f"{tool.name} missing description"

    def test_each_tool_has_input_schema(self) -> None:
        for tool in _TOOLS:
            assert tool.inputSchema, f"{tool.name} missing inputSchema"
            assert "properties" in tool.inputSchema

    def test_search_code_has_required_query(self) -> None:
        tool = next(t for t in _TOOLS if t.name == "search_code")
        assert "query" in tool.inputSchema["required"]

    def test_index_repository_requires_url_and_name(self) -> None:
        tool = next(t for t in _TOOLS if t.name == "index_repository")
        assert "url" in tool.inputSchema["required"]
        assert "name" in tool.inputSchema["required"]


class TestDispatch:
    @pytest.mark.asyncio
    async def test_search_code(self) -> None:
        retrieval = MagicMock()
        retrieval.search_code.return_value = [{"symbol_id": "x", "name": "foo"}]
        result = await _dispatch("search_code", {"query": "hello world"}, retrieval)
        retrieval.search_code.assert_called_once_with(
            query="hello world", limit=10, repo_filter=None, kind_filter=None
        )
        assert result[0]["name"] == "foo"

    @pytest.mark.asyncio
    async def test_get_symbol(self) -> None:
        retrieval = MagicMock()
        retrieval.get_symbol.return_value = {"id": "x", "name": "bar"}
        result = await _dispatch("get_symbol", {"symbol_id": "x"}, retrieval)
        retrieval.get_symbol.assert_called_once_with("x")
        assert result["name"] == "bar"

    @pytest.mark.asyncio
    async def test_find_usages(self) -> None:
        retrieval = MagicMock()
        retrieval.find_usages.return_value = []
        result = await _dispatch("find_usages", {"symbol_id": "x"}, retrieval)
        retrieval.find_usages.assert_called_once_with("x")

    @pytest.mark.asyncio
    async def test_get_dependencies_with_depth(self) -> None:
        retrieval = MagicMock()
        retrieval.get_dependencies.return_value = []
        await _dispatch("get_dependencies", {"symbol_id": "x", "depth": 3}, retrieval)
        retrieval.get_dependencies.assert_called_once_with("x", depth=3)

    @pytest.mark.asyncio
    async def test_analyze_impact(self) -> None:
        retrieval = MagicMock()
        retrieval.analyze_impact.return_value = []
        await _dispatch("analyze_impact", {"symbol_id": "x"}, retrieval)
        retrieval.analyze_impact.assert_called_once_with("x", depth=3)

    @pytest.mark.asyncio
    async def test_get_related_docs(self) -> None:
        retrieval = MagicMock()
        retrieval.get_related_knowledge.return_value = {
            "endpoints": [], "docs": [], "tasks": []
        }
        await _dispatch("get_related_docs", {"symbol_id": "x"}, retrieval)
        retrieval.get_related_knowledge.assert_called_once_with("x")

    @pytest.mark.asyncio
    async def test_recommend(self) -> None:
        retrieval = MagicMock()
        retrieval.recommend.return_value = []
        await _dispatch("recommend", {"symbol_id": "x", "limit": 3}, retrieval)
        retrieval.recommend.assert_called_once_with("x", limit=3)

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self) -> None:
        retrieval = MagicMock()
        result = await _dispatch("nonexistent_tool", {}, retrieval)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_index_repository_returns_started(self) -> None:
        retrieval = MagicMock()
        # Patch _background_index so the background task doesn't contact GitHub
        async def _noop(*args: object, **kwargs: object) -> None:
            pass

        with patch("mysterial.mcp.gateway._background_index", new=_noop):
            result = await _dispatch(
                "index_repository",
                {"url": "https://github.com/org/repo", "name": "repo"},
                retrieval,
            )
        assert result["status"] == "indexing_started"
        assert result["repo"] == "repo"


class TestTextResult:
    def test_wraps_dict_as_json(self) -> None:
        result = _text_result({"key": "value"})
        assert len(result.content) == 1
        data = json.loads(result.content[0].text)
        assert data["key"] == "value"

    def test_wraps_list(self) -> None:
        result = _text_result([1, 2, 3])
        data = json.loads(result.content[0].text)
        assert data == [1, 2, 3]

    def test_handles_none(self) -> None:
        result = _text_result(None)
        assert result.content[0].text == "null"


class TestCreateMCPServer:
    def test_creates_server_without_retrieval(self) -> None:
        server = create_mcp_server(retrieval=None)
        assert server is not None
        assert server.name == "mysterial"
