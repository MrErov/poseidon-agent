"""Tests for prompt artifact contracts."""

from pathlib import Path

from poseidon.prompt_builder import PromptBuilder


def _build_user_content(
    *,
    artifact_path: Path | None = None,
    phase_kind: str | None = None,
    preserve_spec_state: bool = False,
) -> str:
    messages = PromptBuilder().build_messages(
        phase="4",
        spec_path=Path("specs/US-002.spec.md"),
        cold_memory="cold memory",
        artifact_path=artifact_path,
        preserve_spec_state=preserve_spec_state,
        phase_kind=phase_kind,
    )
    return messages[-1]["content"]


def test_drift_prompt_declares_effective_verdict_contract() -> None:
    content = _build_user_content(
        artifact_path=Path("specs/US-002.drift.1.md"), phase_kind="drift"
    )

    assert "effective_verdict" in content
    assert "no-drift | drifted | drifted-accepted" in content


def test_non_drift_prompt_omits_drift_contract() -> None:
    content = _build_user_content(
        artifact_path=Path("specs/US-002.audit.1.md"), phase_kind="goldfish"
    )

    assert "effective_verdict" not in content


def test_tdd_prompt_keeps_spec_state_ownership() -> None:
    content = _build_user_content(preserve_spec_state=True, phase_kind="tdd")

    assert "POSEIDON SPEC OWNERSHIP" in content
    assert "Do not change 'status'" in content
