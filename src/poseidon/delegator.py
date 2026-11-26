"""Delegate prompts to local CLIs through isolated subprocesses."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping

from poseidon.exceptions import DelegationError


class LocalCLIDelegator:
    """Invoke CLIs without a shell, with explicit timeout and output capture."""

    _COMMANDS = {
        "claude-code": "claude",
        "codex": "codex",
        "opencode": "opencode",
    }
    _EXECUTABLE_ENV_VARS = {
        "claude-code": "POSEIDON_CLAUDE_CODE_BIN",
        "codex": "POSEIDON_CODEX_BIN",
        "opencode": "POSEIDON_OPENCODE_BIN",
    }
    _MAX_ERROR_OUTPUT = 2000

    def __init__(
        self,
        timeout_seconds: float = 300.0,
        executables: Mapping[str, str] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self._executables = dict(executables or {})

    def execute(self, prompt: str, cli_type: str, model: str | None = None) -> str:
        """Send a prompt to the selected CLI and return its textual stdout."""
        normalized_cli = cli_type.strip().lower()
        if normalized_cli not in self._COMMANDS:
            supported = ", ".join(sorted(self._COMMANDS))
            raise DelegationError(
                f"Unsupported local CLI: '{cli_type}'. Options: {supported}."
            )
        if not prompt.strip():
            raise DelegationError("Cannot delegate an empty prompt.")

        executable = self._resolve_executable(normalized_cli)
        if normalized_cli == "claude-code":
            command = [executable, "-p", "--output-format", "text"]
        elif normalized_cli == "codex":
            command = [executable, "exec", "-"]
        else:
            command = [executable, "run"]

        if model and model.strip():
            command.extend(["--model", model.strip()])

        run_options: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": self.timeout_seconds,
            "check": False,
            "shell": False,
            "input": prompt,
        }

        try:
            completed = subprocess.run(command, **run_options)
        except subprocess.TimeoutExpired as exc:
            raise DelegationError(
                f"{normalized_cli} exceeded the {self.timeout_seconds}-second timeout."
            ) from exc
        except OSError as exc:
            raise DelegationError(
                f"Could not start {normalized_cli} with '{executable}': {exc}"
            ) from exc

        if completed.returncode != 0:
            details = self._error_details(completed.stderr, completed.stdout)
            raise DelegationError(
                f"{normalized_cli} exited with code {completed.returncode}: {details}"
            )

        output = (completed.stdout or "").strip()
        if not output:
            details = self._error_details(completed.stderr, "")
            raise DelegationError(
                f"{normalized_cli} returned empty output. {details}"
            )

        return output

    def _resolve_executable(self, cli_type: str) -> str:
        override = self._executables.get(cli_type) or os.getenv(
            self._EXECUTABLE_ENV_VARS[cli_type], ""
        ).strip()
        if override:
            return override

        executable = shutil.which(self._COMMANDS[cli_type])
        if executable is None:
            env_var = self._EXECUTABLE_ENV_VARS[cli_type]
            raise DelegationError(
                f"Could not find '{self._COMMANDS[cli_type]}' in PATH. "
                f"Install it or set {env_var}."
            )
        return executable

    @classmethod
    def _error_details(cls, stderr: str | None, stdout: str | None) -> str:
        details = (stderr or stdout or "No additional details.").strip()
        if len(details) > cls._MAX_ERROR_OUTPUT:
            return "…" + details[-cls._MAX_ERROR_OUTPUT :]
        return details
