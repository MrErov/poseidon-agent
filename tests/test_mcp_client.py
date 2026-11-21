from unittest.mock import Mock, patch

import httpx
import pytest

from poseidon.mcp_client import fetch_graph_context


@pytest.mark.parametrize(
    "payload",
    [
        {"context": "core -> cli"},
        {"result": {"content": [{"type": "text", "text": "core -> cli"}]}},
    ],
)
def test_fetch_graph_context_posts_query_and_extracts_text(
    payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAPHIFY_MCP_URL", "https://graphify.test/mcp")
    response = Mock()
    response.json.return_value = payload

    with patch("poseidon.mcp_client.httpx.post", return_value=response) as post:
        result = fetch_graph_context("specs/US-001.spec.md")

    assert result == "core -> cli"
    post.assert_called_once_with(
        "https://graphify.test/mcp",
        json={"query": "specs/US-001.spec.md"},
        timeout=10.0,
    )
    response.raise_for_status.assert_called_once_with()


def test_fetch_graph_context_is_disabled_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPHIFY_MCP_URL", raising=False)

    with patch("poseidon.mcp_client.httpx.post") as post:
        assert fetch_graph_context("spec") == ""

    post.assert_not_called()


def test_fetch_graph_context_returns_empty_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPHIFY_MCP_URL", "https://graphify.test/mcp")

    with patch(
        "poseidon.mcp_client.httpx.post",
        side_effect=httpx.ConnectError("Graphify no disponible"),
    ):
        assert fetch_graph_context("spec") == ""
