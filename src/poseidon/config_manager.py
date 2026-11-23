"""Role and executor resolution for Poseidón's optional config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


class ConfigError(RuntimeError):
    """The YAML configuration is missing, invalid, or inconsistent."""


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
        data = self._load()
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
        runtime = role_settings.get("runtime")
        executor = cli_executor or runtime or role_settings.get("executor") or "api"
        model = cli_model if cli_model is not None else role_settings.get("model")

        agent = role_settings.get("agent")
        if executor == "herdr" and agent is None:
            agent = (
                role_settings.get("executor")
                if runtime == "herdr"
                else "claude-code"
            )

        herdr = dict(base_herdr)
        herdr.update(role_settings.get("herdr", {}) or {})
        if role_settings.get("name_prefix"):
            herdr["name_prefix"] = role_settings["name_prefix"]

        return ExecutionConfig(
            role=selected_role,
            executor=executor,
            model=model,
            agent=agent,
            herdr=herdr,
        )

    def _load(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {}

        try:
            data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ConfigError(f"Could not read {self.config_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"{self.config_path} must contain a YAML mapping.")
        if not isinstance(data.get("roles", {}), dict):
            raise ConfigError("The 'roles' section must be a mapping.")
        if not isinstance(data.get("phase_roles", {}), dict):
            raise ConfigError("The 'phase_roles' section must be a mapping.")
        return data
