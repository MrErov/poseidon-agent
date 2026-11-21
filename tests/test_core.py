from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rich.console import Console

from poseidon.core import GateError, InputValidationError, PhaseRunner


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _write_inputs(tmp_path: Path, phase: str = "1b") -> tuple[Path, Path]:
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir(exist_ok=True)
    phase_file = skills_dir / f"{phase}.md"
    phase_file.write_text("Instrucciones inmutables de la fase.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Especificación\n\nContenido de prueba.", encoding="utf-8")
    return phase_file, spec_file


def _console(output: StringIO) -> Console:
    return Console(file=output, force_terminal=False, color_system=None, width=120)


def _runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: StringIO) -> PhaseRunner:
    monkeypatch.chdir(tmp_path)
    return PhaseRunner(console=_console(output))


def test_goldfish_uses_fresh_hot_memory_on_every_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, spec_file = _write_inputs(tmp_path)
    output = StringIO()
    runner = _runner(tmp_path, monkeypatch, output)

    with patch(
        "poseidon.core.litellm.completion",
        side_effect=[_response("## Primera auditoría"), _response("## Segunda auditoría")],
    ) as completion:
        first_result = runner.run("1b", str(spec_file), "deepseek/deepseek-chat")
        second_result = runner.run("1b", str(spec_file), "deepseek/deepseek-chat")

    assert first_result == "## Primera auditoría"
    assert second_result == "## Segunda auditoría"
    assert completion.call_count == 2

    first_call = completion.call_args_list[0].kwargs
    second_call = completion.call_args_list[1].kwargs
    first_messages = first_call["messages"]
    second_messages = second_call["messages"]

    assert first_messages is not second_messages
    assert first_messages[0] is not second_messages[0]
    assert [message["role"] for message in first_messages] == ["system", "user"]
    assert [message["role"] for message in second_messages] == ["system", "user"]
    assert first_messages[0]["content"] == "Instrucciones inmutables de la fase."
    assert "Contenido de prueba." in first_messages[1]["content"]
    assert first_call["temperature"] == 0.0
    assert second_call["temperature"] == 0.0

    rendered = output.getvalue()
    assert rendered.count("Aislando Memoria para Goldfish") == 2
    assert "Primera auditoría" in rendered
    assert "Segunda auditoría" in rendered


def test_goldfish_detection_uses_phase_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, spec_file = _write_inputs(tmp_path, phase="02-egm-goldfish-audit")
    output = StringIO()
    runner = _runner(tmp_path, monkeypatch, output)

    with patch("poseidon.core.litellm.completion", return_value=_response("Auditado")):
        runner.run("02-egm-goldfish-audit", str(spec_file), "modelo")

    assert "Aislando Memoria para Goldfish" in output.getvalue()


def test_non_goldfish_phase_allows_missing_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inputs(tmp_path, phase="1a")
    output = StringIO()
    runner = _runner(tmp_path, monkeypatch, output)

    with patch(
        "poseidon.core.litellm.completion", return_value=_response("Resultado")
    ) as completion:
        runner.run("1a", None, "openai/gpt-4o-mini")

    assert "Aislando Memoria para Goldfish" not in output.getvalue()
    assert "No se proporcionó una especificación" in completion.call_args.kwargs["messages"][1][
        "content"
    ]


def test_missing_phase_stops_before_calling_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("Especificación", encoding="utf-8")
    runner = _runner(tmp_path, monkeypatch, StringIO())

    with patch("poseidon.core.litellm.completion") as completion:
        with pytest.raises(InputValidationError, match="Memoria Fría"):
            runner.run("1b", str(spec_file), "modelo")

    completion.assert_not_called()


def test_missing_spec_stops_before_calling_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inputs(tmp_path)
    runner = _runner(tmp_path, monkeypatch, StringIO())

    with patch("poseidon.core.litellm.completion") as completion:
        with pytest.raises(InputValidationError, match="especificación"):
            runner.run("1b", str(tmp_path / "missing.md"), "modelo")

    completion.assert_not_called()


def test_phase_name_cannot_escape_skills_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(tmp_path, monkeypatch, StringIO())

    with pytest.raises(InputValidationError, match="solo puede contener"):
        runner.run("../1b", None, "modelo")


@pytest.mark.parametrize("phase", ["2", "03-tdd-cycle"])
def test_gatekeeper_blocks_draft_spec(
    phase: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("---\nstatus: draft\n---\n# Especificación", encoding="utf-8")
    runner = _runner(tmp_path, monkeypatch, StringIO())

    with patch("poseidon.core.litellm.completion") as completion:
        with pytest.raises(GateError) as exc_info:
            runner.run(phase, str(spec_file), "modelo")

    assert str(exc_info.value) == (
        "❌ GATEKEEPER BLOQUEÓ LA FASE: El spec no ha pasado la auditoría Goldfish "
        "(status actual: draft). Ejecuta la Fase 1b primero."
    )
    completion.assert_not_called()


@pytest.mark.parametrize("status", ["audited", "approved"])
def test_gatekeeper_allows_audited_spec(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, spec_file = _write_inputs(tmp_path, phase="2")
    spec_file.write_text(f"---\nstatus: {status}\n---\n# Especificación", encoding="utf-8")
    runner = _runner(tmp_path, monkeypatch, StringIO())

    with patch(
        "poseidon.core.litellm.completion", return_value=_response("TDD iniciado")
    ) as completion:
        result = runner.run("2", str(spec_file), "modelo")

    assert result == "TDD iniciado"
    completion.assert_called_once()
