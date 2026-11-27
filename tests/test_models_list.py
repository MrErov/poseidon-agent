"""Tests for ``poseidon models list``."""

from pathlib import Path

from typer.testing import CliRunner

from poseidon.main import app
from poseidon.model_router import DEFAULT_MODEL_ROUTING

cli = CliRunner()


def test_models_list_shows_builtin_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "240")

    result = cli.invoke(app, ["models", "list"])

    assert result.exit_code == 0, result.output
    for role in ("planner", "coder", "reviewer", "default"):
        assert role in result.output
    assert DEFAULT_MODEL_ROUTING.planner in result.output
    assert DEFAULT_MODEL_ROUTING.reviewer in result.output
    assert "No config.yaml found" in result.output
    assert "poseidon config init" in result.output


def test_models_list_reads_configured_routing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "240")
    (tmp_path / "config.yaml").write_text(
        """version: 2
default_role: tester
roles:
  tester:
    executor: api
model_routing:
  planner: custom/planner
  coder: custom/coder
  reviewer: custom/reviewer
  default: custom/default
""",
        encoding="utf-8",
    )

    result = cli.invoke(app, ["models", "list"])

    assert result.exit_code == 0, result.output
    for model in (
        "custom/planner",
        "custom/coder",
        "custom/reviewer",
        "custom/default",
    ):
        assert model in result.output
    assert "Source: config.yaml" in result.output


def test_models_list_reports_invalid_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("unknown_key: true\n", encoding="utf-8")

    result = cli.invoke(app, ["models", "list"])

    assert result.exit_code == 1
    assert "Configuration error" in result.output
