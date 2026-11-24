"""Constructor de prompts para las fases de Keel Nav."""

from __future__ import annotations

import os
from pathlib import Path

from poseidon.mcp_client import fetch_graph_context


class PromptBuilder:
    """Construye la lista de mensajes (Memoria Caliente) para una ejecución."""

    def __init__(self, console=None):
        self.console = console

    def build_messages(
        self,
        phase: str,
        spec_path: Path | None,
        cold_memory: str,
        specification: str | None = None,
        context: str | None = None,
        graph_context: str | None = None,
    ) -> list[dict[str, str]]:
        """Crea una lista nueva de mensajes; nunca reutiliza historial previo."""
        if spec_path is None:
            intro = (
                f"Ejecuta la fase '{phase}'.\n\n"
                "No se proporcionó una especificación de entrada para esta fase."
            )
        else:
            intro = f"Ejecuta la fase '{phase}' sobre la especificación '{spec_path}'."

        blocks: list[str] = []
        if context is not None:
            blocks.append(
                "--- INICIO DEL CONTEXTO ---\n"
                f"{context}\n"
                "--- FIN DEL CONTEXTO ---"
            )
        if graph_context:
            blocks.append(
                "--- INICIO DEL GRAFO DE CÓDIGO (Graphify MCP) ---\n"
                f"{graph_context}\n"
                "--- FIN DEL GRAFO DE CÓDIGO (Graphify MCP) ---"
            )
        if specification is not None:
            blocks.append(
                "--- INICIO DE LA ESPECIFICACIÓN ---\n"
                f"{specification}\n"
                "--- FIN DE LA ESPECIFICACIÓN ---"
            )

        user_content = "\n\n".join([intro, *blocks])

        return [
            {"role": "system", "content": cold_memory},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def format_for_cli(messages: list[dict[str, str]]) -> str:
        """Serializa mensajes para pasarlos por stdin a un CLI local."""
        return "\n\n".join(
            f"--- {msg['role'].upper()} ---\n{msg['content']}" for msg in messages
        )

    @staticmethod
    def fetch_graph_context_if_needed(
        phase_kind: str,
        spec_file: Path | None,
        context_file: Path | None,
    ) -> str:
        """Obtiene contexto de Graphify si está habilitado y la fase lo requiere."""
        if phase_kind not in {"spec", "goldfish"}:
            return ""

        url = os.getenv("GRAPHIFY_MCP_URL", "").strip()
        if not url:
            return ""

        query_target = spec_file or context_file
        query = str(query_target) if query_target is not None else ""
        if not query:
            return ""

        try:
            return fetch_graph_context(query)
        except Exception:
            # Fallo tolerante: no interrumpir la ejecución
            return ""