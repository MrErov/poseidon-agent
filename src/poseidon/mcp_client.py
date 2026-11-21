"""Cliente HTTP tolerante a fallos para Graphify MCP."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_GRAPHIFY_MCP_URL = "https://api.graphify.com/mcp"
_REQUEST_TIMEOUT_SECONDS = 10.0


def fetch_graph_context(query: str) -> str:
    """Obtiene contexto de Graphify sin interrumpir la ejecución de Poseidón.

    La integración es opt-in: sin GRAPHIFY_MCP_URL no se realiza ninguna
    petición. El valor predeterminado documentado para esa variable es
    DEFAULT_GRAPHIFY_MCP_URL.
    """
    url = os.getenv("GRAPHIFY_MCP_URL", "").strip()
    if not url:
        return ""

    try:
        response = httpx.post(
            url,
            json={"query": query},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, TypeError, ValueError):
        return ""

    return _extract_text(payload)


def _extract_text(payload: Any) -> str:
    """Acepta respuestas de texto simples o estructuras MCP con contenido textual."""
    if isinstance(payload, str):
        return payload

    if isinstance(payload, list):
        return "\n".join(
            text for item in payload if (text := _extract_text(item))
        )

    if isinstance(payload, dict):
        for key in ("context", "text", "content", "result"):
            if key in payload and (text := _extract_text(payload[key])):
                return text

    return ""
