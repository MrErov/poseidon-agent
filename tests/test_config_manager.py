from pathlib import Path

import pytest

from poseidon.config_manager import ConfigError, ConfigManager


def _write_config(path: Path) -> None:
    path.write_text(
        """version: 2
roles:
  architect:
    executor: api
    model: nvidia_nim/architect-model
  tester:
    executor: claude-code
    model: null
    runtime: herdr
    name_prefix: poseidon-tester
phase_roles:
  0: architect
  1b: tester
herdr:
  executable: hc
  wait_timeout_seconds: 180
  read_lines: 1000
""",
        encoding="utf-8",
    )


def test_phase_role_resolves_herdr_and_role_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    result = ConfigManager(config).resolve("1b")

    assert result.role == "tester"
    assert result.executor == "herdr"
    assert result.model is None
    assert result.agent == "claude-code"
    assert result.herdr["name_prefix"] == "poseidon-tester"
    assert result.herdr["wait_timeout_seconds"] == 180


def test_explicit_role_overrides_phase_role(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    result = ConfigManager(config).resolve("1b", role="architect")

    assert result.role == "architect"
    assert result.executor == "api"
    assert result.model == "nvidia_nim/architect-model"


def test_cli_executor_and_model_override_role(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    result = ConfigManager(config).resolve(
        "1b", cli_executor="api", cli_model="nvidia_nim/custom"
    )

    assert result.executor == "api"
    assert result.model == "nvidia_nim/custom"
    assert result.agent is None


def test_missing_config_uses_defaults(tmp_path: Path) -> None:
    result = ConfigManager(tmp_path / "missing.yaml").resolve("1b")

    assert result.role is None
    assert result.executor == "api"
    assert result.model is None


def test_unknown_role_raises_controlled_error(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    with pytest.raises(ConfigError, match="not defined"):
        ConfigManager(config).resolve("1b", role="missing")


def test_canonical_phase_name_uses_phase_zero_role(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    result = ConfigManager(config).resolve("00-context-bootstrap")

    assert result.role == "architect"
