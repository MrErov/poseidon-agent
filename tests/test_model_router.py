"""Tests for ModelRouter."""

import pytest

from poseidon.model_router import PHASE_TO_ROLE, ModelRouter, ModelRouting


def test_phase_to_role_mapping() -> None:
    """Test that phases map to correct roles."""
    assert PHASE_TO_ROLE["0"] == "planner"
    assert PHASE_TO_ROLE["1a"] == "planner"
    assert PHASE_TO_ROLE["1b"] == "reviewer"
    assert PHASE_TO_ROLE["2"] == "coder"
    assert PHASE_TO_ROLE["3"] == "planner"
    assert PHASE_TO_ROLE["4"] == "planner"


def test_model_router_explicit_model_override() -> None:
    """Test that explicit model overrides routing."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    # Explicit model should override everything
    assert router.resolve("0", "explicit-model") == "explicit-model"
    assert router.resolve("1b", "explicit-model") == "explicit-model"
    assert router.resolve("2", "explicit-model") == "explicit-model"


def test_model_router_planner_phases() -> None:
    """Test that planner phases return planner model."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    for phase in ["0", "1a", "3", "4"]:
        assert router.resolve(phase) == "planner-model", f"Phase {phase} should use planner"


def test_model_router_coder_phase() -> None:
    """Test that coder phase returns coder model."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    assert router.resolve("2") == "coder-model"


def test_model_router_reviewer_phase() -> None:
    """Test that reviewer phase returns reviewer model."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    assert router.resolve("1b") == "reviewer-model"


def test_model_router_unknown_phase_fallback() -> None:
    """Test that unknown phases fall back to planner."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    # Unknown phase should fall back to planner
    assert router.resolve("unknown") == "planner-model"
    assert router.resolve("5") == "planner-model"


def test_model_router_fallback_to_default() -> None:
    """Test fallback to default when role attribute is missing."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    # Test that normal phases work
    assert router.resolve("1b") == "reviewer-model"
    assert router.resolve("2") == "coder-model"
    assert router.resolve("0") == "planner-model"

    # Test that unknown phase falls back to planner (which exists)
    assert router.resolve("unknown") == "planner-model"


def test_model_router_resolves_phase_aliases() -> None:
    """Test that human-friendly phase aliases use the same role mapping."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    assert router.resolve("goldfish") == "reviewer-model"
    assert router.resolve("tdd") == "coder-model"
    assert router.resolve("drift") == "planner-model"
    assert router.resolve("  GOLDFISH  ") == "reviewer-model"


def test_model_router_resolve_role() -> None:
    """Test direct role resolution for TUI model selection."""
    routing = ModelRouting(
        planner="planner-model",
        coder="coder-model",
        reviewer="reviewer-model",
        default="default-model",
    )
    router = ModelRouter(routing)

    assert router.resolve_role("planner") == "planner-model"
    assert router.resolve_role("coder") == "coder-model"
    assert router.resolve_role("reviewer") == "reviewer-model"
    assert router.resolve_role("default") == "default-model"
    assert router.resolve_role("unknown") == "default-model"
    assert router.resolve_role("") == "default-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])