"""Tests for the interactive ``poseidon config init`` wizard."""

from pathlib import Path
from types import SimpleNamespace

import yaml
from typer.testing import CliRunner

from poseidon.config_manager import ConfigManager, create_default_config, save_config
from poseidon.main import _CUSTOM_MODEL, app
from poseidon.model_router import DEFAULT_MODEL_ROUTING

cli = CliRunner()

PLANNER = "nvidia_nim/moonshotai/kimi-k2-instruct"
CODER = "nvidia_nim/nemotron-3-ultra-550b-a55b"
REVIEWER = "nvidia_nim/mistralai/mistral-large-4-1t-a52b"


def _select_answers(values: list[str]):
    """Return a questionary.select replacement that yields ``values`` in order."""
    answers = iter(values)

    def fake_select(*args, **kwargs):
        return SimpleNamespace(ask=lambda: next(answers))

    return fake_select


def test_config_init_creates_complete_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "poseidon.main.questionary.select",
        _select_answers([PLANNER, CODER, REVIEWER]),
    )

    result = cli.invoke(app, ["config", "init"])

    assert result.exit_code == 0, result.output
    config_path = tmp_path / "config.yaml"
    assert config_path.is_file()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["model_routing"] == {
        "planner": PLANNER,
        "coder": CODER,
        "reviewer": REVIEWER,
        "default": CODER,
    }
    assert data["default_role"] == "tester"
    assert data["roles"]["architect"] == {"executor": "api"}
    assert data["roles"]["tester"] == {"executor": "api"}
    assert "herdr" in data

    # The generated file must be accepted by the real validator.
    assert ConfigManager(config_path).get_model_routing().planner == PLANNER
    assert "config.yaml created successfully" in result.output
    assert "poseidon doctor" in result.output


def test_config_init_seeds_defaults_from_existing_config(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """version: 2
default_role: tester
roles:
  tester:
    executor: codex
phase_roles:
  0: tester
herdr:
  executable: hc
  wait_timeout_seconds: 123
model_routing:
  planner: custom/planner
  coder: custom/coder
  reviewer: custom/reviewer
  default: custom/default
""",
        encoding="utf-8",
    )

    seen_defaults: list[str] = []

    def fake_select(prompt, choices=None, default=None):
        seen_defaults.append(default)
        return SimpleNamespace(ask=lambda: default)

    monkeypatch.setattr("poseidon.main.questionary.select", fake_select)

    result = cli.invoke(app, ["config", "init", "--force"])

    assert result.exit_code == 0, result.output
    assert seen_defaults == ["custom/planner", "custom/coder", "custom/reviewer"]

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["roles"]["tester"]["executor"] == "codex"
    assert data["phase_roles"] == {0: "tester"}
    assert data["herdr"]["wait_timeout_seconds"] == 123
    assert data["model_routing"]["default"] == "custom/default"


def test_config_init_accepts_custom_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "poseidon.main.questionary.select",
        _select_answers([_CUSTOM_MODEL, CODER, REVIEWER]),
    )
    monkeypatch.setattr(
        "poseidon.main.questionary.text",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: "ollama/llama3"),
    )

    result = cli.invoke(app, ["config", "init"])

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert data["model_routing"]["planner"] == "ollama/llama3"


def test_config_init_cancel_keeps_existing_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    original = "version: 2\nroles:\n  tester:\n    executor: api\n"
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "poseidon.main.questionary.confirm",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: False),
    )

    result = cli.invoke(app, ["config", "init"])

    assert result.exit_code == 0, result.output
    assert "Cancelled" in result.output
    assert config_path.read_text(encoding="utf-8") == original


def test_config_init_rejects_invalid_existing_config(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("unknown_key: true\n", encoding="utf-8")

    result = cli.invoke(app, ["config", "init"])

    assert result.exit_code == 1
    assert "Configuration error" in result.output


def test_create_and_save_default_config(tmp_path: Path) -> None:
    target = save_config(create_default_config(), tmp_path / "nested" / "config.yaml")

    assert target.is_file()
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["model_routing"]["planner"] == DEFAULT_MODEL_ROUTING.planner
    assert data["model_routing"]["coder"] == DEFAULT_MODEL_ROUTING.coder
    assert data["model_routing"]["reviewer"] == DEFAULT_MODEL_ROUTING.reviewer
    assert data["model_routing"]["default"] == DEFAULT_MODEL_ROUTING.default
