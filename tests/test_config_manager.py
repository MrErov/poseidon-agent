from pathlib import Path

import pytest

from poseidon.config_manager import ConfigError, ConfigManager, ConfigValidationError


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


def test_herdr_defaults_are_900_seconds_and_persistent(tmp_path: Path) -> None:
    result = ConfigManager(tmp_path / "missing.yaml").resolve("1b")

    assert result.herdr["wait_timeout_seconds"] == 900
    assert result.herdr["mode"] == "persistent"


def test_unknown_herdr_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "herdr:\n  fallback_to_subprocess: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="Unknown Herdr settings"):
        ConfigManager(config).resolve("1b")


def test_unknown_role_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "    name_prefix: poseidon-tester",
            "    name_prefix: poseidon-tester\n    unexpected: true",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="unknown keys"):
        ConfigManager(config).resolve("1b")


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("unknown: true\n")

    with pytest.raises(ConfigValidationError, match="top-level"):
        ConfigManager(config).resolve("1b")


@pytest.mark.parametrize("mode", ["headless", "persistent"])
def test_valid_herdr_modes_are_allowed(mode: str, tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write(f"  mode: {mode}\n")

    result = ConfigManager(config).resolve("1b")

    assert result.herdr["mode"] == mode


def test_invalid_herdr_mode_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  mode: invalid\n")

    with pytest.raises(ConfigValidationError, match="mode must be one of"):
        ConfigManager(config).resolve("1b")


def test_phase_role_non_string_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "roles:\n  tester:\n    executor: api\n"
        "phase_roles:\n  1b: [tester]\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="role reference must be a string"):
        ConfigManager(config).resolve("1b")


@pytest.mark.parametrize("launch", ["interactive", "headless_in_terminal"])
def test_valid_herdr_launch_values_are_allowed(launch: str, tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write(f"  launch: {launch}\n")

    result = ConfigManager(config).resolve("1b")

    assert result.herdr["launch"] == launch


def test_invalid_herdr_launch_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  launch: invalid\n")

    with pytest.raises(ConfigValidationError, match="launch must be one of"):
        ConfigManager(config).resolve("1b")


def test_herdr_launch_defaults_to_headless_in_terminal(tmp_path: Path) -> None:
    result = ConfigManager(tmp_path / "missing.yaml").resolve("1b")

    assert result.herdr["launch"] == "headless_in_terminal"
    assert result.herdr["agent_model"] == ""
    assert result.herdr["agent_args"] == []


def test_agent_model_must_be_a_string(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  agent_model: 123\n")

    with pytest.raises(ConfigValidationError, match="agent_model"):
        ConfigManager(config).resolve("1b")


def test_agent_args_must_be_a_list_of_strings(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  agent_args: [--format, 123]\n")

    with pytest.raises(ConfigValidationError, match="only strings"):
        ConfigManager(config).resolve("1b")


def test_agent_args_must_be_a_list(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  agent_args: '--format'\n")

    with pytest.raises(ConfigValidationError, match="agent_args"):
        ConfigManager(config).resolve("1b")


def test_role_model_is_used_as_herdr_agent_model(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "    model: null", "    model: nvidia/test-model"
        ),
        encoding="utf-8",
    )

    result = ConfigManager(config).resolve("1b")

    assert result.herdr["agent_model"] == "nvidia/test-model"


def test_cli_model_overrides_role_agent_model(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)

    result = ConfigManager(config).resolve(
        "1b", cli_model="nvidia/custom-model"
    )

    assert result.herdr["agent_model"] == "nvidia/custom-model"


def test_auto_approve_must_be_boolean(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_config(config)
    with config.open("a", encoding="utf-8") as handle:
        handle.write("  auto_approve: 'yes'\n")

    with pytest.raises(ConfigValidationError, match="auto_approve"):
        ConfigManager(config).resolve("1b")
