"""Tests for paper search functionality."""

import pytest
import json
from unittest.mock import patch
from arxiv_mcp_server.tools import handle_search


@pytest.mark.asyncio
async def test_basic_search(mock_client):
    """Test basic paper search functionality."""
    with patch("arxiv_mcp_server.tools.search.MyArxivClient", return_value=mock_client):
        result = await handle_search({"query": "test query", "max_results": 1})

        assert len(result) == 1
        content = json.loads(result[0].text)
        assert content["total_results"] == 1
        paper = content["papers"][0]
        assert paper["id"] == "2103.12345"
        assert paper["title"] == "Test Paper"
        assert "resource_uri" in paper


@pytest.mark.asyncio
async def test_search_with_categories(mock_client):
    """Test paper search with category filtering."""
    with patch("arxiv_mcp_server.tools.search.MyArxivClient", return_value=mock_client):
        result = await handle_search(
            {"query": "test query", "categories": ["cs.AI", "cs.LG"], "max_results": 1}
        )

        content = json.loads(result[0].text)
        # The mock paper has both categories, so this should work
        assert content["papers"][0]["categories"] == ["cs.AI", "cs.LG"]


@pytest.mark.asyncio
async def test_search_with_dates(mock_client):
    """Test paper search with date filtering."""
    with patch("arxiv_mcp_server.tools.search.MyArxivClient", return_value=mock_client):
        result = await handle_search(
            {
                "query": "test query",
                "date_from": "2022-01-01",
                "date_to": "2024-01-01",
                "max_results": 1,
            }
        )

        content = json.loads(result[0].text)
        assert content["total_results"] == 1
        assert len(content["papers"]) == 1


@pytest.mark.asyncio
async def test_search_with_invalid_dates(mock_client):
    """Test search with invalid date formats."""
    with patch("arxiv_mcp_server.tools.search.MyArxivClient", return_value=mock_client):
        result = await handle_search(
            {"query": "test query", "date_from": "invalid-date", "max_results": 1}
        )

        # The error message format has changed
        assert result[0].text.startswith("Error: Unknown string format")


@pytest.mark.asyncio
async def test_search_query_field_specifier_fix(mock_client):
    """Test that plain queries get field specifiers for better relevance (issue #33)."""
    with patch("arxiv_mcp_server.tools.search.MyArxivClient", return_value=mock_client):
        with patch("arxiv.Search") as search_mock:
            # Test multi-word query - now includes date range automatically
            await handle_search({"query": "quantum computing", "max_results": 1})
            search_mock.assert_called()
            query = search_mock.call_args[1]["query"]
            assert "all:quantum+AND+all:computing" in query
            assert "submittedDate:" in query

            # Test single word query
            search_mock.reset_mock()
            await handle_search({"query": "transformer", "max_results": 1})
            query = search_mock.call_args[1]["query"]
            assert "all:transformer" in query
            assert "submittedDate:" in query

            # Test query with existing field specifier (should not be modified)
            search_mock.reset_mock()
            await handle_search({"query": "ti:neural networks", "max_results": 1})
            query = search_mock.call_args[1]["query"]
            assert "ti:neural+AND+networks" in query
            assert "submittedDate:" in query
