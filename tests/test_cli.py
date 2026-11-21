from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from poseidon.main import app

cli = CliRunner()


def _response(content: str = "## Respuesta") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_run_command_executes_requested_phase(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Instrucciones Goldfish", encoding="utf-8"
    )
    spec = tmp_path / "spec.md"
    spec.write_text("Especificación de prueba", encoding="utf-8")

    with patch("poseidon.core.litellm.completion", return_value=_response()) as completion:
        result = cli.invoke(
            app,
            [
                "run",
                "--phase",
                "1b",
                "--spec",
                str(spec),
                "--model",
                "deepseek/deepseek-chat",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Aislando Memoria para Goldfish" in result.output
    assert "Respuesta" in result.output
    assert completion.call_args.kwargs["model"] == "deepseek/deepseek-chat"


def test_run_command_injects_context_before_spec(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Instrucciones Goldfish", encoding="utf-8"
    )
    spec = tmp_path / "US-001.md"
    spec.write_text("Especificación de prueba", encoding="utf-8")
    context = tmp_path / "api.md"
    context.write_text("Contexto de API", encoding="utf-8")

    with patch("poseidon.core.litellm.completion", return_value=_response()) as completion:
        result = cli.invoke(
            app,
            [
                "run",
                "--phase",
                "1b",
                "--spec",
                str(spec),
                "--context",
                str(context),
                "--model",
                "modelo",
            ],
        )

    assert result.exit_code == 0, result.output
    user_content = completion.call_args.kwargs["messages"][1]["content"]
    assert "Contexto de API" in user_content
    assert user_content.index("Contexto de API") < user_content.index("Especificación de prueba")
    assert (tmp_path / "specs" / "US-001.audit.1.md").is_file()


def test_cli_reports_missing_phase_in_red_error_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("Especificación", encoding="utf-8")

    with patch("poseidon.core.litellm.completion") as completion:
        result = cli.invoke(
            app,
            ["run", "--phase", "1b", "--spec", str(spec), "--model", "modelo"],
        )

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Memoria Fría" in result.output
    completion.assert_not_called()


def test_cli_reports_missing_spec_and_does_not_call_litellm(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Instrucciones Goldfish", encoding="utf-8"
    )

    with patch("poseidon.core.litellm.completion") as completion:
        result = cli.invoke(
            app,
            [
                "run",
                "--phase",
                "1b",
                "--spec",
                str(tmp_path / "missing.md"),
                "--model",
                "modelo",
            ],
        )

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "especificación" in result.output
    completion.assert_not_called()
