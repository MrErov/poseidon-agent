"""Delegación de prompts a CLIs locales mediante subprocesos aislados."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping


class DelegationError(RuntimeError):
    """Un CLI local no pudo ejecutar el prompt o devolvió una salida inválida."""


class LocalCLIDelegator:
    """Invoca CLIs sin shell, con timeout y captura explícita de salida."""

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
            raise ValueError("timeout_seconds debe ser mayor que cero")
        self.timeout_seconds = timeout_seconds
        self._executables = dict(executables or {})

    def execute(self, prompt: str, cli_type: str) -> str:
        """Envía un prompt al CLI seleccionado y devuelve su stdout textual."""
        normalized_cli = cli_type.strip().lower()
        if normalized_cli not in self._COMMANDS:
            supported = ", ".join(sorted(self._COMMANDS))
            raise DelegationError(
                f"CLI local no soportado: '{cli_type}'. Opciones: {supported}."
            )
        if not prompt.strip():
            raise DelegationError("No se puede delegar un prompt vacío.")

        executable = self._resolve_executable(normalized_cli)
        if normalized_cli == "claude-code":
            command = [executable, "-p", "--output-format", "text"]
        elif normalized_cli == "codex":
            command = [executable, "exec", prompt]
        else:
            command = [executable, "run", prompt]

        run_options: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": self.timeout_seconds,
            "check": False,
            "shell": False,
        }
        if normalized_cli == "claude-code":
            run_options["input"] = prompt
        else:
            run_options["stdin"] = subprocess.DEVNULL

        try:
            completed = subprocess.run(command, **run_options)
        except subprocess.TimeoutExpired as exc:
            raise DelegationError(
                f"{normalized_cli} superó el timeout de {self.timeout_seconds} segundos."
            ) from exc
        except OSError as exc:
            raise DelegationError(
                f"No se pudo iniciar {normalized_cli} con '{executable}': {exc}"
            ) from exc

        if completed.returncode != 0:
            details = self._error_details(completed.stderr, completed.stdout)
            raise DelegationError(
                f"{normalized_cli} terminó con código {completed.returncode}: {details}"
            )

        output = (completed.stdout or "").strip()
        if not output:
            details = self._error_details(completed.stderr, "")
            raise DelegationError(
                f"{normalized_cli} devolvió una salida vacía. {details}"
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
                f"No se encontró '{self._COMMANDS[cli_type]}' en PATH. "
                f"Instálalo o configura {env_var}."
            )
        return executable

    @classmethod
    def _error_details(cls, stderr: str | None, stdout: str | None) -> str:
        details = (stderr or stdout or "Sin detalles adicionales.").strip()
        if len(details) > cls._MAX_ERROR_OUTPUT:
            return "…" + details[-cls._MAX_ERROR_OUTPUT :]
        return details
