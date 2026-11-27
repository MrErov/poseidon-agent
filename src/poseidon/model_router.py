"""Model routing for phase-based multi-model orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRouting:
    """Model assignments per role."""
    planner: str
    coder: str
    reviewer: str
    default: str


# Phase to role mapping
PHASE_TO_ROLE = {
    "0": "planner",
    "1a": "planner",
    "1b": "reviewer",
    "2": "coder",
    "3": "planner",
    "4": "planner",
}


class ModelRouter:
    """Resolves the appropriate model for a given phase."""

    def __init__(self, routing: ModelRouting) -> None:
        self.routing = routing

    def resolve(self, phase: str, explicit_model: str | None = None) -> str:
        """
        Resolve the model for a given phase.

        Args:
            phase: The phase identifier (e.g., "0", "1a", "1b", "2", "3", "4").
            explicit_model: An explicitly provided model that overrides routing.

        Returns:
            The model identifier to use.
        """
        if explicit_model is not None:
            return explicit_model

        role = PHASE_TO_ROLE.get(phase, "planner")
        return getattr(self.routing, role, self.routing.default)