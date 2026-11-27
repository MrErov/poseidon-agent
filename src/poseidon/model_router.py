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


DEFAULT_MODEL_ROUTING = ModelRouting(
    planner="nvidia_nim/moonshotai/kimi-k2-instruct",
    coder="nvidia_nim/nemotron-3-ultra-550b-a55b",
    reviewer="nvidia_nim/mistralai/mistral-large-4-1t-a52b",
    default="nvidia_nim/nemotron-3-ultra-550b-a55b",
)

# Canonical phase aliases shared with ConfigManager.
PHASE_ALIASES = {
    "0": "0",
    "00": "0",
    "context": "0",
    "00-context-bootstrap": "0",
    "1a": "1a",
    "spec": "1a",
    "01-sdd-spec-writer": "1a",
    "1b": "1b",
    "goldfish": "1b",
    "02-egm-goldfish-audit": "1b",
    "2": "2",
    "tdd": "2",
    "03-tdd-cycle": "2",
    "3": "3",
    "odd": "3",
    "04-odd-vertical-slice": "3",
    "4": "4",
    "drift": "4",
    "05-drift-control": "4",
}

# Canonical phase to orchestration role.
PHASE_TO_ROLE = {
    "0": "planner",
    "1a": "planner",
    "1b": "reviewer",
    "2": "coder",
    "3": "planner",
    "4": "planner",
}


class ModelRouter:
    """Resolve the appropriate model for a phase or orchestration role."""

    def __init__(self, routing: ModelRouting) -> None:
        self.routing = routing

    def resolve_role(self, role: str) -> str:
        """Return the model configured for a role, falling back to ``default``."""
        if not isinstance(role, str) or not role:
            return self.routing.default
        return getattr(self.routing, role, None) or self.routing.default

    def resolve(self, phase: str, explicit_model: str | None = None) -> str:
        """Resolve the model for a phase.

        Args:
            phase: Phase identifier or alias (for example ``"1b"`` or ``"goldfish"``).
            explicit_model: An explicitly provided model that overrides routing.

        Returns:
            The model identifier to use.
        """
        if explicit_model is not None:
            return explicit_model

        normalized = phase.strip().lower()
        phase_id = PHASE_ALIASES.get(normalized, normalized)
        return self.resolve_role(PHASE_TO_ROLE.get(phase_id, "planner"))
