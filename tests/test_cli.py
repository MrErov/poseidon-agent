from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
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
    assert "Isolating memory for Goldfish" in result.output
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
    assert "Cold memory" in result.output
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
    assert "Specification file" in result.output
    completion.assert_not_called()


def test_cli_local_executor_does_not_require_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "00-context-bootstrap.md").write_text("Mapea el repositorio", encoding="utf-8")
    completed = SimpleNamespace(returncode=0, stdout="# Mapa", stderr="")

    with (
        patch("poseidon.delegator.shutil.which", return_value="claude"),
        patch("poseidon.delegator.subprocess.run", return_value=completed) as run,
        patch("poseidon.core.litellm.completion") as completion,
    ):
        result = cli.invoke(
            app,
            ["run", "--phase", "0", "--executor", "claude-code"],
        )

    assert result.exit_code == 0, result.output
    run.assert_called_once()
    completion.assert_not_called()


def test_cli_api_executor_requires_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    with patch("poseidon.core.litellm.completion") as completion:
        result = cli.invoke(app, ["run", "--phase", "0"])

    assert result.exit_code == 1
    assert "--model is required" in result.output
    completion.assert_not_called()


def test_cli_role_selects_herdr(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text("Goldfish", encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("Spec under test", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        """version: 2
roles:
  tester:
    executor: claude-code
    model: null
    runtime: herdr
    name_prefix: poseidon-tester
phase_roles:
  1b: tester
herdr:
  executable: hc
  wait_timeout_seconds: 180
""",
        encoding="utf-8",
    )
    herdr = Mock()
    herdr.execute.return_value = "verdict: rejected"

    with (
        patch("poseidon.main.HerdrDelegator.from_settings", return_value=herdr) as from_settings,
        patch("poseidon.core.litellm.completion") as completion,
    ):
        result = cli.invoke(app, ["run", "--phase", "1b", "--role", "tester"])

    assert result.exit_code == 0, result.output
    from_settings.assert_called_once()
    assert herdr.execute.call_args.args[1] == "claude-code"
    completion.assert_not_called()


def test_cli_debug_flag_reaches_herdr_delegator(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "00-context-bootstrap.md").write_text("Map repository", encoding="utf-8")
    herdr = Mock()
    herdr.execute.return_value = "## Context map"

    with (
        patch("poseidon.main.HerdrDelegator.from_settings", return_value=herdr) as from_settings,
        patch("poseidon.core.litellm.completion") as completion,
    ):
        result = cli.invoke(app, ["run", "--phase", "0", "--executor", "herdr", "--debug"])

    assert result.exit_code == 0, result.output
    from_settings.assert_called_once()
    assert from_settings.call_args.kwargs["debug"] is True
    completion.assert_not_called()


def test_cli_resume_does_not_launch_new_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "00-context-bootstrap.md").write_text(
        "Map repository", encoding="utf-8"
    )
    herdr = Mock()
    herdr.resume.return_value = "Final context map"

    with patch("poseidon.main.HerdrDelegator.from_settings", return_value=herdr) as from_settings:
        result = cli.invoke(
            app, ["run", "--phase", "0", "--executor", "herdr", "--resume", "t19"]
        )

    assert result.exit_code == 0, result.output
    from_settings.assert_called_once()
    herdr.resume.assert_called_once_with("t19")
    herdr.execute.assert_not_called()


def test_cli_auto_detects_single_spec(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Goldfish instructions", encoding="utf-8"
    )
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    spec = specs_dir / "US-002.spec.md"
    spec.write_text("---\nstatus: draft\n---\n# US-002\n", encoding="utf-8")

    with patch(
        "poseidon.core.litellm.completion",
        return_value=_response("---\nverdict: audited\n---\n# Audit"),
    ) as completion:
        result = cli.invoke(app, ["run", "--phase", "1b", "--model", "modelo"])

    assert result.exit_code == 0, result.output
    assert "ℹ️ Auto-detected spec: specs/US-002.spec.md" in result.output
    prompt = completion.call_args.kwargs["messages"][1]["content"]
    assert "# US-002" in prompt


@pytest.mark.parametrize("args", [["run"], ["run", "-i"]])
def test_cli_wizard_runs_selected_phase(
    args: list[str], tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Goldfish instructions", encoding="utf-8"
    )
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "US-002.spec.md").write_text(
        "---\nstatus: draft\n---\n# US-002\n", encoding="utf-8"
    )
    (tmp_path / "config.yaml").write_text(
        """version: 2
default_role: tester
roles:
  tester:
    executor: api
    model: test-model
""",
        encoding="utf-8",
    )
    answers = iter(["1b", "specs/US-002.spec.md", "tester"])
    questions: list[str] = []

    def fake_select(message, choices=None, default=None):
        questions.append(message)
        return SimpleNamespace(ask=lambda: next(answers))

    with (
        patch("poseidon.main.questionary.select", side_effect=fake_select),
        patch(
            "poseidon.core.litellm.completion",
            return_value=_response("---\nverdict: audited\n---\n# Audit"),
        ) as completion,
    ):
        result = cli.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert questions == ["Phase:", "Spec:", "Role:"]
    completion.assert_called_once()


def test_status_shows_phases_specs_and_default_role(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    skills_dir = tmp_path / ".meta-skills"
    skills_dir.mkdir()
    (skills_dir / "02-egm-goldfish-audit.md").write_text(
        "Goldfish instructions", encoding="utf-8"
    )
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "US-002.spec.md").write_text(
        "---\nstatus: certified\n---\n# US-002\n", encoding="utf-8"
    )
    (tmp_path / "config.yaml").write_text(
        """version: 2
default_role: tester
roles:
  tester:
    executor: api
    model: test-model
""",
        encoding="utf-8",
    )

    result = cli.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "Default role" in result.output
    assert "tester" in result.output
    assert "1b" in result.output
    assert "specs/US-002.spec.md" in result.output
    assert "certified" in result.output
