"""Role and executor resolution for Poseidón's optional config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from poseidon.exceptions import ConfigError, ConfigValidationError

_PHASE_IDS = {
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


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution settings resolved from CLI, role, phase, and defaults."""

    role: str | None
    executor: str
    model: str | None
    agent: str | None
    herdr: dict[str, Any]


class ConfigManager:
    """Resolve agent roles without imposing a configuration on other projects."""

    _VALID_EXECUTORS = {"api", "claude-code", "codex", "opencode", "herdr"}
    _VALID_RUNTIMES = {"api", "herdr"}
    _HERDR_DEFAULTS = {
        "executable": "hc",
        "wait_timeout_seconds": 180.0,
        "read_lines": 1000,
        "keep": True,
        "outlive_parent": True,
        "name_prefix": "poseidon",
        "connection_timeout_seconds": 30.0,
    }
    _HERDR_TYPES = {
        "executable": str,
        "wait_timeout_seconds": (int, float),
        "read_lines": int,
        "keep": bool,
        "outlive_parent": bool,
        "name_prefix": str,
        "connection_timeout_seconds": (int, float),
    }

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            Path(config_path) if config_path is not None else Path.cwd() / "config.yaml"
        )

    def resolve(
        self,
        phase: str,
        role: str | None = None,
        cli_executor: str | None = None,
        cli_model: str | None = None,
    ) -> ExecutionConfig:
        """Resolve execution using CLI > role > phase role > default precedence."""
        data = self._load_and_validate()
        roles = data.get("roles", {}) or {}
        phase_roles = {
            str(key).lower(): value for key, value in (data.get("phase_roles", {}) or {}).items()
        }
        normalized_phase = phase.strip().lower()
        phase_id = _PHASE_IDS.get(normalized_phase, normalized_phase)
        selected_role = role or phase_roles.get(phase_id)
        base_herdr = dict(data.get("herdr", {}) or {})

        if selected_role is None:
            executor = cli_executor or "api"
            self._validate_executor(executor)
            return ExecutionConfig(
                role=None,
                executor=executor,
                model=cli_model,
                agent="claude-code" if executor == "herdr" else None,
                herdr=base_herdr,
            )

        if selected_role not in roles:
            raise ConfigError(f"Role '{selected_role}' is not defined in {self.config_path}.")

        role_settings = roles[selected_role] or {}
        self._validate_role_settings(role_settings, selected_role)

        runtime = role_settings.get("runtime")
        if runtime is not None:
            self._validate_runtime(runtime)

        executor = cli_executor or runtime or role_settings.get("executor") or "api"
        self._validate_executor(executor)

        model = cli_model if cli_model is not None else role_settings.get("model")

        agent = role_settings.get("agent")
        if executor == "herdr" and agent is None:
            agent = (
                role_settings.get("executor") if runtime == "herdr" else "claude-code"
            )

        herdr = dict(base_herdr)
        herdr.update(role_settings.get("herdr", {}) or {})
        if role_settings.get("name_prefix"):
            herdr["name_prefix"] = role_settings["name_prefix"]

        # Validate and coerce herdr settings
        self._validate_herdr_settings(herdr)

        return ExecutionConfig(
            role=selected_role,
            executor=executor,
            model=model,
            agent=agent,
            herdr=herdr,
        )

    def _validate_executor(self, executor: str) -> None:
        if executor not in self._VALID_EXECUTORS:
            options = ", ".join(sorted(self._VALID_EXECUTORS))
            raise ConfigValidationError(
                f"Executor '{executor}' no es válido. Opciones: {options}"
            )

    def _validate_runtime(self, runtime: str) -> None:
        if runtime not in self._VALID_RUNTIMES:
            options = ", ".join(sorted(self._VALID_RUNTIMES))
            raise ConfigValidationError(
                f"Runtime '{runtime}' no es válido. Opciones: {options}"
            )

    def _validate_role_settings(self, settings: dict[str, Any], role_name: str) -> None:
        if not isinstance(settings, dict):
            raise ConfigValidationError(f"Role '{role_name}' must be a mapping.")

        executor = settings.get("executor")
        if executor is not None and not isinstance(executor, str):
            raise ConfigValidationError(
                f"Role '{role_name}': 'executor' must be a string, got {type(executor).__name__}"
            )

        model = settings.get("model")
        if model is not None and not isinstance(model, str):
            raise ConfigValidationError(
                f"Role '{role_name}': 'model' must be a string, got {type(model).__name__}"
            )

        agent = settings.get("agent")
        if agent is not None and not isinstance(agent, str):
            raise ConfigValidationError(
                f"Role '{role_name}': 'agent' must be a string, got {type(agent).__name__}"
            )

        runtime = settings.get("runtime")
        if runtime is not None and not isinstance(runtime, str):
            raise ConfigValidationError(
                f"Role '{role_name}': 'runtime' must be a string, got {type(runtime).__name__}"
            )

        name_prefix = settings.get("name_prefix")
        if name_prefix is not None and not isinstance(name_prefix, str):
            raise ConfigValidationError(
                "Role '{role_name}': 'name_prefix' must be a string, "
                f"got {type(name_prefix).__name__}"
            )

        herdr = settings.get("herdr")
        if herdr is not None and not isinstance(herdr, dict):
            raise ConfigValidationError(
                f"Role '{role_name}': 'herdr' must be a mapping, got {type(herdr).__name__}"
            )

    def _validate_herdr_settings(self, herdr: dict[str, Any]) -> None:
        for key, expected_type in self._HERDR_TYPES.items():
            value = herdr.get(key)
            if value is None:
                continue
            if isinstance(expected_type, tuple):
                if not isinstance(value, expected_type):
                    type_names = [t.__name__ for t in expected_type]
                    raise ConfigValidationError(
                        f"Herdr setting '{key}' must be one of {type_names}, "
                        f"got {type(value).__name__}: {value!r}"
                    )
            elif not isinstance(value, expected_type):
                raise ConfigValidationError(
                    f"Herdr setting '{key}' must be {expected_type.__name__}, "
                    f"got {type(value).__name__}: {value!r}"
                )

        # Validate numeric ranges
        wait_timeout = herdr.get("wait_timeout_seconds")
        if wait_timeout is not None and wait_timeout <= 0:
            raise ConfigValidationError("Herdr 'wait_timeout_seconds' must be greater than zero")

        conn_timeout = herdr.get("connection_timeout_seconds")
        if conn_timeout is not None and conn_timeout <= 0:
            raise ConfigValidationError(
                "Herdr 'connection_timeout_seconds' must be greater than zero"
            )

        read_lines = herdr.get("read_lines")
        if read_lines is not None and read_lines < 0:
            raise ConfigValidationError("Herdr 'read_lines' cannot be negative")

    def _load_and_validate(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {}

        try:
            data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ConfigError(f"Could not read {self.config_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"{self.config_path} must contain a YAML mapping.")

        roles = data.get("roles", {})
        if not isinstance(roles, dict):
            raise ConfigError("The 'roles' section must be a mapping.")

        for role_name, role_settings in roles.items():
            if not isinstance(role_settings, dict):
                raise ConfigError(f"Role '{role_name}' must be a mapping.")
            if "executor" in role_settings and not isinstance(role_settings["executor"], str):
                raise ConfigValidationError(
                    f"Role '{role_name}': 'executor' must be a string"
                )
            if "runtime" in role_settings and not isinstance(role_settings["runtime"], str):
                raise ConfigValidationError(
                    f"Role '{role_name}': 'runtime' must be a string"
                )
            if "model" in role_settings:
                model_val = role_settings["model"]
                if model_val is not None and not isinstance(model_val, str):
                    raise ConfigValidationError(
                        f"Role '{role_name}': 'model' must be a string or null"
                    )
            if "agent" in role_settings and not isinstance(role_settings["agent"], str):
                raise ConfigValidationError(
                    f"Role '{role_name}': 'agent' must be a string"
                )
            if "name_prefix" in role_settings and not isinstance(
                role_settings["name_prefix"], str
            ):
                raise ConfigValidationError(
                    f"Role '{role_name}': 'name_prefix' must be a string"
                )
            if "herdr" in role_settings and not isinstance(role_settings["herdr"], dict):
                raise ConfigValidationError(
                    f"Role '{role_name}': 'herdr' must be a mapping"
                )

        phase_roles = data.get("phase_roles", {})
        if not isinstance(phase_roles, dict):
            raise ConfigError("The 'phase_roles' section must be a mapping.")

        herdr = data.get("herdr", {})
        if not isinstance(herdr, dict):
            raise ConfigError("The 'herdr' section must be a mapping.")

        return data