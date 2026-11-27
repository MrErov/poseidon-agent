"""Prompt builder for Keel Nav phases."""

from __future__ import annotations

import os
from pathlib import Path

from poseidon.mcp_client import fetch_graph_context

_FRONTMATTER_CONTRACTS = {
    "drift": "effective_verdict: <no-drift | drifted | drifted-accepted>",
}


class PromptBuilder:
    """Build the message list (hot memory) for one run."""

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
        artifact_path: Path | None = None,
        preserve_spec_state: bool = False,
        phase_kind: str | None = None,
        resumed_messages: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Create a message list, optionally resuming from prior history.

        Args:
            resumed_messages: Optional prior message history to prepend (for API resume).
        """
        if spec_path is None:
            intro = (
                f"Run phase '{phase}'.\n\n"
                "No input specification was provided for this phase."
            )
        else:
            intro = f"Run phase '{phase}' against spec '{spec_path}'."

        blocks: list[str] = []
        if context is not None:
            blocks.append(
                "--- CONTEXT START ---\n"
                f"{context}\n"
                "--- CONTEXT END ---"
            )
        if artifact_path is not None:
            artifact_lines = [
                "--- POSEIDON ARTIFACT OWNERSHIP ---",
                f"Write your artifact to '{artifact_path.as_posix()}' "
                "(exact path; do not choose another).",
            ]
            contract = _FRONTMATTER_CONTRACTS.get(phase_kind or "")
            if contract is not None:
                artifact_lines.extend(
                    [
                        "Your artifact must begin with YAML frontmatter "
                        "containing at least:",
                        contract,
                        "Use exactly these field names; Poseidon validates them.",
                    ]
                )
            artifact_lines.extend(
                [
                    "Do not change 'status', 'goldfish_audit', or "
                    "'drift_report' in the spec frontmatter.",
                    "Poseidon will apply the state transition itself.",
                ]
            )
            blocks.append("\n".join(artifact_lines))
        elif preserve_spec_state:
            blocks.append(
                "--- POSEIDON SPEC OWNERSHIP ---\n"
                "Do not change 'status', 'goldfish_audit', or "
                "'drift_report' in the spec frontmatter.\n"
                "Poseidon will apply the state transition itself."
            )
        if graph_context:
            blocks.append(
                "--- CODE GRAPH START (Graphify MCP) ---\n"
                f"{graph_context}\n"
                "--- CODE GRAPH END (Graphify MCP) ---"
            )
        if specification is not None:
            blocks.append(
                "--- SPECIFICATION START ---\n"
                f"{specification}\n"
                "--- SPECIFICATION END ---"
            )

        user_content = "\n\n".join([intro, *blocks])

        messages = [
            {"role": "system", "content": cold_memory},
            {"role": "user", "content": user_content},
        ]

        # Prepend resumed history if provided (for API resume)
        if resumed_messages:
            # Skip the system message from resumed history to avoid duplication
            resumed_filtered = [m for m in resumed_messages if m.get("role") != "system"]
            messages = resumed_filtered + messages

        return messages

    @staticmethod
    def format_for_cli(messages: list[dict[str, str]]) -> str:
        """Serialize messages for stdin delivery to a local CLI."""
        return "\n\n".join(
            f"--- {msg['role'].upper()} ---\n{msg['content']}" for msg in messages
        )

    @staticmethod
    def fetch_graph_context_if_needed(
        phase_kind: str,
        spec_file: Path | None,
        context_file: Path | None,
    ) -> str:
        """Fetch Graphify context when enabled and required by the phase."""
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
            # Tolerant failure: do not interrupt the run
            return ""
