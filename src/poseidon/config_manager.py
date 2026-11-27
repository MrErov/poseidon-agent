"""Role and executor resolution for Poseidón's optional config.yaml."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from poseidon.exceptions import ConfigError, ConfigValidationError
from poseidon.model_router import (
    DEFAULT_MODEL_ROUTING,
    PHASE_ALIASES,
    ModelRouting,
)
from poseidon.utils import get_working_dir


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

    DEFAULT_ROLE = "tester"
    _VALID_EXECUTORS = {"api", "claude-code", "codex", "opencode", "herdr"}
    _VALID_RUNTIMES = {"api", "herdr"}
    _VALID_MODES = {"persistent", "headless"}
    _VALID_LAUNCHES = {"interactive", "headless_in_terminal"}
    _TOP_LEVEL_KEYS = {"version", "default_role", "roles", "phase_roles", "herdr", "model_routing"}
    _ROLE_KEYS = {"executor", "model", "runtime", "agent", "name_prefix", "herdr"}
    _HERDR_DEFAULTS = {
        "executable": "hc",
        "wait_timeout_seconds": 900.0,
        "read_lines": 1000,
        "keep": True,
        "outlive_parent": True,
        "name_prefix": "poseidon",
        "connection_timeout_seconds": 30.0,
        "mode": "persistent",
        "launch": "headless_in_terminal",
        "agent_model": "",
        "agent_args": [],
        "auto_approve": True,
        "total_timeout_seconds": 3600.0,
        "progress_interval_seconds": 30.0,
        "phase_timeouts": {},
    }
    _HERDR_TYPES = {
        "executable": str,
        "wait_timeout_seconds": (int, float),
        "read_lines": int,
        "keep": bool,
        "outlive_parent": bool,
        "name_prefix": str,
        "connection_timeout_seconds": (int, float),
        "mode": str,
        "launch": str,
        "agent_model": str,
        "agent_args": list,
        "auto_approve": bool,
        "total_timeout_seconds": (int, float),
        "progress_interval_seconds": (int, float),
        "phase_timeouts": dict,
    }

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            Path(config_path) if config_path is not None else get_working_dir() / "config.yaml"
        )

    @property
    def default_role(self) -> str:
        """Return the configured default role, falling back to ``tester``."""
        data = self._load_and_validate()
        value = data.get("default_role")
        return value or self.DEFAULT_ROLE

    def get_model_routing(self) -> ModelRouting:
        """Return the model routing configuration."""
        data = self._load_and_validate()
        mr = data.get("model_routing", {}) or {}
        return ModelRouting(
            planner=mr.get("planner") or DEFAULT_MODEL_ROUTING.planner,
            coder=mr.get("coder") or DEFAULT_MODEL_ROUTING.coder,
            reviewer=mr.get("reviewer") or DEFAULT_MODEL_ROUTING.reviewer,
            default=mr.get("default") or DEFAULT_MODEL_ROUTING.default,
        )

    def load(self) -> dict[str, Any]:
        """Return validated configuration data, or an empty mapping if absent."""
        return self._load_and_validate()

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
        phase_id = PHASE_ALIASES.get(normalized_phase, normalized_phase)
        selected_role = role or phase_roles.get(phase_id)
        if selected_role is None:
            default_role = data.get("default_role") or self.DEFAULT_ROLE
            if default_role in roles:
                selected_role = default_role
        base_herdr = self._HERDR_DEFAULTS | dict(data.get("herdr", {}) or {})
        self._validate_herdr_settings(base_herdr)

        if selected_role is None:
            executor = cli_executor or "api"
            self._validate_executor(executor)
            if executor == "herdr" and cli_model:
                base_herdr["agent_model"] = cli_model
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

        herdr = self._HERDR_DEFAULTS | dict(data.get("herdr", {}) or {})
        herdr.update(role_settings.get("herdr", {}) or {})
        if executor == "herdr":
            herdr["agent_model"] = (
                cli_model
                or role_settings.get("agent_model")
                or role_settings.get("model")
                or herdr.get("agent_model", "")
            )
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
                f"Invalid executor '{executor}'. Options: {options}"
            )

    def _validate_runtime(self, runtime: str) -> None:
        if runtime not in self._VALID_RUNTIMES:
            options = ", ".join(sorted(self._VALID_RUNTIMES))
            raise ConfigValidationError(
                f"Invalid runtime '{runtime}'. Options: {options}"
            )

    def _validate_role_settings(self, settings: dict[str, Any], role_name: str) -> None:
        if not isinstance(settings, dict):
            raise ConfigValidationError(f"Role '{role_name}' must be a mapping.")

        unknown_keys = set(settings) - self._ROLE_KEYS
        if unknown_keys:
            raise ConfigValidationError(
                f"Role '{role_name}' has unknown keys: {sorted(unknown_keys)}"
            )

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
        unknown_keys = set(herdr) - set(self._HERDR_TYPES)
        if unknown_keys:
            raise ConfigValidationError(
                f"Unknown Herdr settings: {sorted(unknown_keys)}"
            )

        mode = herdr.get("mode")
        if mode is not None and mode not in self._VALID_MODES:
            options = ", ".join(sorted(self._VALID_MODES))
            raise ConfigValidationError(
                f"Herdr mode must be one of: {options}; got {mode!r}"
            )

        launch = herdr.get("launch")
        if launch is not None and launch not in self._VALID_LAUNCHES:
            options = ", ".join(sorted(self._VALID_LAUNCHES))
            raise ConfigValidationError(
                f"Herdr launch must be one of: {options}; got {launch!r}"
            )

        agent_args = herdr.get("agent_args")
        if agent_args is not None and any(
            not isinstance(arg, str) for arg in agent_args
        ):
            raise ConfigValidationError(
                "Herdr 'agent_args' must contain only strings"
            )

        phase_timeouts = herdr.get("phase_timeouts")
        if phase_timeouts is not None:
            if not isinstance(phase_timeouts, dict):
                raise ConfigValidationError(
                    "Herdr 'phase_timeouts' must be a mapping"
                )
            for phase, timeout in phase_timeouts.items():
                if not isinstance(phase, str):
                    raise ConfigValidationError(
                        "Herdr 'phase_timeouts' keys must be strings"
                    )
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    raise ConfigValidationError(
                        f"Herdr phase '{phase}' timeout must be greater than zero"
                    )

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

        unknown_keys = set(data) - self._TOP_LEVEL_KEYS
        if unknown_keys:
            raise ConfigValidationError(
                f"Unknown top-level configuration keys: {sorted(unknown_keys)}"
            )

        default_role = data.get("default_role")
        if default_role is not None and not isinstance(default_role, str):
            raise ConfigValidationError("'default_role' must be a string")

        roles = data.get("roles", {})
        if not isinstance(roles, dict):
            raise ConfigError("The 'roles' section must be a mapping.")

        if default_role is not None and default_role not in roles:
            raise ConfigValidationError(
                f"'default_role' references undefined role '{default_role}'"
            )

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
        for phase_name, role_name in phase_roles.items():
            if not isinstance(role_name, str):
                raise ConfigValidationError(
                    f"Phase '{phase_name}': role reference must be a string"
                )

        herdr = data.get("herdr", {})
        if not isinstance(herdr, dict):
            raise ConfigError("The 'herdr' section must be a mapping.")

        model_routing = data.get("model_routing", {})
        if model_routing:
            if not isinstance(model_routing, dict):
                raise ConfigError("The 'model_routing' section must be a mapping.")
            required_keys = {"planner", "coder", "reviewer", "default"}
            missing = required_keys - set(model_routing)
            if missing:
                raise ConfigValidationError(
                    f"'model_routing' missing required keys: {sorted(missing)}"
                )
            for key, value in model_routing.items():
                if not isinstance(value, str):
                    raise ConfigValidationError(
                        f"'model_routing.{key}' must be a string"
                    )

        return data


_DEFAULT_PHASE_ROLES = {
    0: "architect",
    "1a": "architect",
    "1b": "tester",
    2: "tester",
    3: "tester",
    4: "architect",
}


def create_default_config(
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete, valid config mapping seeded from ``existing`` values."""
    source = dict(existing or {})
    routing = source.get("model_routing") or {}

    roles = source.get("roles")
    if not roles:
        # Leave role models unset so ModelRouter selects the model per phase.
        roles = {
            "architect": {"executor": "api"},
            "tester": {"executor": "api"},
        }

    default_role = source.get("default_role") or ConfigManager.DEFAULT_ROLE
    if default_role not in roles:
        default_role = next(iter(roles), ConfigManager.DEFAULT_ROLE)

    herdr = deepcopy(ConfigManager._HERDR_DEFAULTS)
    herdr.update(source.get("herdr") or {})

    return {
        "version": source.get("version", 2),
        "default_role": default_role,
        "roles": roles,
        "phase_roles": source.get("phase_roles") or dict(_DEFAULT_PHASE_ROLES),
        "herdr": herdr,
        "model_routing": {
            "planner": routing.get("planner") or DEFAULT_MODEL_ROUTING.planner,
            "coder": routing.get("coder") or DEFAULT_MODEL_ROUTING.coder,
            "reviewer": routing.get("reviewer") or DEFAULT_MODEL_ROUTING.reviewer,
            "default": routing.get("default") or DEFAULT_MODEL_ROUTING.default,
        },
    }


def save_config(
    config: Mapping[str, Any],
    path: str | Path | None = None,
) -> Path:
    """Write ``config`` to ``path`` atomically and return the target path."""
    target = Path(path) if path is not None else get_working_dir() / "config.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(
        dict(config),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Poseidon configuration\n")
            handle.write("# Generated by `poseidon config init`.\n")
            handle.write(payload)
        os.replace(temp_name, target)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        raise

    return target
