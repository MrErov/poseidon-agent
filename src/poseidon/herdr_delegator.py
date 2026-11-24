"""Persistent agent delegation through herdr-core's JSON-RPC stdio API."""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich.console import Console

from poseidon.exceptions import DelegationError


class HerdrDelegator:
    """Run agents in herdr-core without owning their process lifetime."""

    _AGENTS = {
        "claude-code": "claude",
        "codex": "codex",
        "opencode": "opencode",
    }

    def __init__(
        self,
        executable: str = "hc",
        wait_timeout_seconds: float = 180.0,
        read_lines: int = 1000,
        keep: bool = True,
        outlive_parent: bool = True,
        name_prefix: str = "poseidon",
        connection_timeout_seconds: float = 30.0,
        console: Console | None = None,
    ) -> None:
        if wait_timeout_seconds <= 0 or connection_timeout_seconds <= 0:
            raise ValueError("Herdr timeouts must be greater than zero")
        if read_lines < 0:
            raise ValueError("read_lines cannot be negative")

        self.executable = executable
        self.wait_timeout_seconds = wait_timeout_seconds
        self.read_lines = read_lines
        self.keep = keep
        self.outlive_parent = outlive_parent
        self.name_prefix = name_prefix
        self.connection_timeout_seconds = connection_timeout_seconds
        self.console = console or Console()
        self._request_id = 0

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None = None) -> HerdrDelegator:
        """Build a delegator from the Herdr section of config.yaml."""
        values = dict(settings or {})
        return cls(
            executable=str(values.get("executable", "hc")),
            wait_timeout_seconds=float(values.get("wait_timeout_seconds", 180)),
            read_lines=int(values.get("read_lines", 1000)),
            keep=bool(values.get("keep", True)),
            outlive_parent=bool(values.get("outlive_parent", True)),
            name_prefix=str(values.get("name_prefix", "poseidon")),
            connection_timeout_seconds=float(
                values.get("connection_timeout_seconds", 30)
            ),
        )

    def execute(self, prompt: str, cli_type: str) -> str:
        """Start, prompt, wait for, and read a persistent Herdr terminal."""
        normalized_cli = cli_type.strip().lower()
        if normalized_cli not in self._AGENTS:
            supported = ", ".join(sorted(self._AGENTS))
            raise DelegationError(
                f"Unsupported Herdr agent '{cli_type}'. Options: {supported}."
            )
        if not prompt.strip():
            raise DelegationError("Cannot send an empty prompt to Herdr.")

        terminal_name = f"{self.name_prefix}-{uuid.uuid4().hex[:16]}"
        run_result = self._call(
            "terminal.run",
            {
                "argv": [self._AGENTS[normalized_cli]],
                "name": terminal_name,
                "cwd": str(Path.cwd()),
                "wait": False,
                "no_parent": True,
                "outlive_parent": self.outlive_parent,
                "keep": self.keep,
            },
        )
        address = self._get_str_field(
            run_result, "address", "Herdr did not return a terminal address."
        )

        prompt_with_enter = prompt if prompt.endswith("\n") else prompt + "\n"
        try:
            self._call(
                "terminal.send",
                {"terminal": address, "text": prompt_with_enter, "wait": False},
            )
            self.console.print(
                f"⏳ Agente lanzado en terminal {address}. Esperando a que termine...",
                style="cyan",
            )
            self.console.print(
                "💡 Si el agente se queda pidiendo permisos, abre otra terminal y usa: "
                f"hc attach {address}",
                style="yellow",
            )
            wait_result = self._call(
                "terminal.wait",
                {"terminal": address, "timeout": self.wait_timeout_seconds},
            )
            ended = self._get_bool_field(wait_result, "ended", False)
            if not ended:
                raise DelegationError(
                    f"Herdr terminal {address} is still running; "
                    f"attach with `hc attach {address}`."
                )

            read_result = self._call(
                "terminal.read",
                {"terminal": address, "lines": self.read_lines},
            )
            exit_code = wait_result.get("exit_code")
            if exit_code not in (None, 0):
                raise DelegationError(
                    f"Herdr terminal {address} exited with code {exit_code}."
                )

            # Verify the read is complete
            complete = self._get_bool_field(read_result, "complete", False)
            if not complete:
                raise DelegationError(
                    f"Herdr terminal {address} read was truncated (complete=false). "
                    f"Output may be incomplete."
                )

            output = self._get_str_field(read_result, "text", "")
            if not output.strip():
                raise DelegationError(f"Herdr terminal {address} returned empty output.")
            return output
        except DelegationError as exc:
            raise DelegationError(
                f"{exc} Terminal {address} remains available; "
                f"inspect it with `hc attach {address}`."
            ) from exc

    @staticmethod
    def _get_str_field(data: Any, field: str, error_msg: str) -> str:
        """Safely extract a string field from a JSON-RPC result dict."""
        if not isinstance(data, dict):
            raise DelegationError(f"Expected dict for JSON-RPC result, got {type(data).__name__}")
        value = data.get(field)
        if not isinstance(value, str) or not value:
            raise DelegationError(error_msg)
        return value

    @staticmethod
    def _get_bool_field(data: Any, field: str, default: bool = False) -> bool:
        """Safely extract a boolean field from a JSON-RPC result dict."""
        if not isinstance(data, dict):
            raise DelegationError(f"Expected dict for JSON-RPC result, got {type(data).__name__}")
        value = data.get(field)
        if isinstance(value, bool):
            return value
        return default

    def _call(self, method: str, params: Mapping[str, Any]) -> Any:
        """Send one JSON-RPC request and return its matching result."""
        self._request_id += 1
        request_id = self._request_id
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            },
            ensure_ascii=False,
        ) + "\n"
        timeout = self._timeout_for(method)

        try:
            process = subprocess.Popen(
                [self.executable, "connect"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise DelegationError(
                "Herdr is not installed or 'hc' is not in PATH. "
                "Install herdr-core and verify the installation."
            ) from exc
        except OSError as exc:
            raise DelegationError(f"Could not start 'hc connect': {exc}") from exc

        try:
            stdout, stderr = process.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise DelegationError(
                f"Herdr request '{method}' exceeded {timeout} seconds."
            ) from exc

        if process.returncode != 0:
            details = (stderr or stdout or "No error details provided.").strip()
            raise DelegationError(
                f"'hc connect' exited with code {process.returncode}: {details}"
            )

        for line in stdout.splitlines():
            try:
                message = json.loads(line)
            except (TypeError, ValueError):
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                if not isinstance(error, dict):
                    raise DelegationError(
                        f"Herdr {method} returned invalid error (not an object): {error}"
                    )
                raise self._rpc_error(method, error)
            if "result" in message:
                result = message["result"]
                if not isinstance(result, dict):
                    raise DelegationError(
                        f"Herdr {method} returned invalid result (not an object): {result}"
                    )
                return result

        raise DelegationError(
            f"Herdr returned no matching response for '{method}'."
        )

    def _timeout_for(self, method: str) -> float:
        if method == "terminal.wait":
            return max(
                self.connection_timeout_seconds,
                self.wait_timeout_seconds + 5,
            )
        return self.connection_timeout_seconds

    @staticmethod
    def _rpc_error(method: str, error: Mapping[str, Any]) -> DelegationError:
        message = str(error.get("message", "Unknown JSON-RPC error"))
        data = error.get("data")
        hint = data.get("hint") if isinstance(data, dict) else None
        suffix = f" {hint}" if hint else ""
        return DelegationError(f"Herdr {method} failed: {message}.{suffix}".rstrip())
