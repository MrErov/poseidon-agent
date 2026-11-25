"""Persistent and headless agent delegation through herdr-core JSON-RPC."""

from __future__ import annotations

import base64
import json
import queue
import subprocess
import threading
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich.console import Console

from poseidon.console import configure_utf8_output
from poseidon.exceptions import DelegationError

_EOF = object()


class _HerdrSession:
    """Own one hc connect process and serialize requests over its stdio."""

    def __init__(self, delegator: HerdrDelegator) -> None:
        self.delegator = delegator
        self.process: Any = None
        self._responses: queue.Queue[Any] = queue.Queue()
        self._stderr: list[str] = []

    def __enter__(self) -> _HerdrSession:
        try:
            self.process = subprocess.Popen(
                [self.delegator.executable, "connect"],
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

        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            daemon=True,
            name="poseidon-herdr-stdout",
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            daemon=True,
            name="poseidon-herdr-stderr",
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._stdout_thread.join(timeout=1)
        self._stderr_thread.join(timeout=1)

    def _read_stdout(self) -> None:
        try:
            for line in self.process.stdout:
                self._responses.put(line)
        except Exception as exc:
            self._responses.put(exc)
        finally:
            self._responses.put(_EOF)

    def _read_stderr(self) -> None:
        try:
            for line in self.process.stderr:
                self._stderr.append(line.rstrip())
        except Exception:
            pass

    def call(self, method: str, params: Mapping[str, Any]) -> Any:
        self.delegator._request_id += 1
        request_id = self.delegator._request_id
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": dict(params),
        }
        payload = json.dumps(request, ensure_ascii=False) + "\n"
        timeout = self.delegator._timeout_for(method)
        try:
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise DelegationError(f"Could not write to 'hc connect': {exc}") from exc

        while True:
            try:
                item = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                raise DelegationError(
                    f"Herdr request '{method}' exceeded {timeout} seconds."
                ) from exc

            if item is _EOF:
                self._check_process_exit(method)
                raise DelegationError(
                    f"Herdr returned no matching response for '{method}'."
                )
            if isinstance(item, Exception):
                raise DelegationError(f"Could not read Herdr response: {item}") from item

            try:
                message = json.loads(item)
            except (TypeError, ValueError):
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if "error" in message:
                raise self.delegator._rpc_error(method, message["error"])
            if "result" not in message:
                continue
            result = message["result"]
            if not isinstance(result, dict):
                raise DelegationError(
                    f"Herdr {method} returned invalid result type "
                    f"'{type(result).__name__}'."
                )
            return result

    def _check_process_exit(self, method: str) -> None:
        try:
            code = self.process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            code = self.process.poll()

        details = "\n".join(self._stderr[-20:]).strip()
        if code not in (None, 0):
            details = details or "No error details provided."
            raise DelegationError(
                f"'hc connect' exited with code {code} during {method}: {details}"
            )
        if details:
            raise DelegationError(
                f"Herdr returned no matching response for '{method}': {details}"
            )


class HerdrDelegator:
    """Run persistent agents without owning their process lifetime."""

    _AGENTS = {
        "claude-code": "claude",
        "codex": "codex",
        "opencode": "opencode",
    }

    def __init__(
        self,
        executable: str = "hc",
        wait_timeout_seconds: float = 900.0,
        read_lines: int = 1000,
        keep: bool = True,
        outlive_parent: bool = True,
        name_prefix: str = "poseidon",
        connection_timeout_seconds: float = 30.0,
        console: Console | None = None,
        mode: str = "persistent",
        launch: str = "headless_in_terminal",
        agent_model: str = "",
        agent_args: list[str] | None = None,
    ) -> None:
        if wait_timeout_seconds <= 0 or connection_timeout_seconds <= 0:
            raise ValueError("Herdr timeouts must be greater than zero")
        if read_lines < 0:
            raise ValueError("read_lines cannot be negative")
        if mode not in {"persistent", "headless"}:
            raise ValueError("Herdr mode must be 'persistent' or 'headless'")
        if launch not in {"interactive", "headless_in_terminal"}:
            raise ValueError(
                "Herdr launch must be 'interactive' or 'headless_in_terminal'"
            )

        self.executable = executable
        self.wait_timeout_seconds = float(wait_timeout_seconds)
        self.read_lines = read_lines
        self.keep = keep
        self.outlive_parent = outlive_parent
        self.name_prefix = name_prefix
        self.connection_timeout_seconds = float(connection_timeout_seconds)
        self.console = console or Console()
        configure_utf8_output()
        self.mode = mode
        self.launch = launch
        self.agent_model = agent_model.strip()
        self.agent_args = list(agent_args or [])
        self._request_id = 0

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None = None) -> HerdrDelegator:
        """Build a delegator from the Herdr section of config.yaml."""
        values = dict(settings or {})
        return cls(
            executable=str(values.get("executable", "hc")),
            wait_timeout_seconds=float(values.get("wait_timeout_seconds", 900)),
            read_lines=int(values.get("read_lines", 1000)),
            keep=bool(values.get("keep", True)),
            outlive_parent=bool(values.get("outlive_parent", True)),
            name_prefix=str(values.get("name_prefix", "poseidon")),
            connection_timeout_seconds=float(
                values.get("connection_timeout_seconds", 30)
            ),
            mode=str(values.get("mode", "persistent")),
            launch=str(values.get("launch", "headless_in_terminal")),
            agent_model=str(values.get("agent_model", "")),
            agent_args=list(values.get("agent_args", [])),
        )

    def execute(self, prompt: str, cli_type: str) -> str:
        """Execute one prompt using a single JSON-RPC connection."""
        normalized_cli = cli_type.strip().lower()
        if normalized_cli not in self._AGENTS:
            supported = ", ".join(sorted(self._AGENTS))
            raise DelegationError(
                f"Unsupported Herdr agent '{cli_type}'. Options: {supported}."
            )
        if not prompt.strip():
            raise DelegationError("Cannot send an empty prompt to Herdr.")

        with _HerdrSession(self) as session:
            if self.mode == "headless":
                return self._execute_headless(session, prompt, normalized_cli)
            if self.launch == "headless_in_terminal":
                return self._execute_headless_terminal(session, prompt, normalized_cli)
            return self._execute_persistent(session, prompt, normalized_cli)

    def _execute_persistent(
        self, session: _HerdrSession, prompt: str, cli_type: str
    ) -> str:
        terminal_name = f"{self.name_prefix}-{uuid.uuid4().hex[:16]}"
        run_result = session.call(
            "terminal.run",
            {
                "argv": [self._AGENTS[cli_type]],
                "name": terminal_name,
                "cwd": str(Path.cwd()),
                "wait": False,
                "no_parent": True,
                "outlive_parent": self.outlive_parent,
                "keep": self.keep,
            },
        )
        address = run_result.get("address")
        if not isinstance(address, str) or not address:
            raise DelegationError("Herdr did not return a terminal address.")

        self._print_wait_feedback(address)
        try:
            send_result = session.call(
                "terminal.send",
                {
                    "caller": address,
                    "terminal": address,
                    "text": prompt,
                    "wait": True,
                    "timeout": self.wait_timeout_seconds,
                },
            )
            wait_result = send_result.get("wait")
            if wait_result is None:
                wait_result = session.call(
                    "terminal.wait",
                    {
                        "caller": address,
                        "terminal": address,
                        "timeout": self.wait_timeout_seconds,
                    },
                )
            self._print_wait_result(wait_result)
            self._validate_wait_result(address, wait_result)

            read_result = session.call(
                "terminal.read",
                {
                    "caller": address,
                    "terminal": address,
                    "lines": self.read_lines,
                },
            )
            self._validate_read_result(address, read_result)
            output = read_result["text"]
            if not output.strip():
                raise DelegationError(f"Herdr terminal {address} returned empty output.")
            return output
        except DelegationError as exc:
            raise DelegationError(
                f"{exc} Terminal {address} remains available; "
                f"inspect it with `hc attach {address}`."
            ) from exc

    def _execute_headless_terminal(
        self, session: _HerdrSession, prompt: str, cli_type: str
    ) -> str:
        prompt_path = self._write_prompt_file(prompt)
        address = "unknown"
        try:
            run_result = session.call(
                "terminal.run",
                {
                    "line": self._headless_command_line(prompt_path, cli_type),
                    "name": f"{self.name_prefix}-{uuid.uuid4().hex[:16]}",
                    "cwd": str(Path.cwd()),
                    "wait": False,
                    "no_parent": True,
                    "outlive_parent": self.outlive_parent,
                    "keep": self.keep,
                },
            )
            address = run_result.get("address")
            if not isinstance(address, str) or not address:
                raise DelegationError("Herdr did not return a terminal address.")

            self._print_wait_feedback(address)
            wait_result = session.call(
                "terminal.wait",
                {"terminal": address, "timeout": self.wait_timeout_seconds},
            )
            self._print_wait_result(wait_result)
            self._validate_wait_result(address, wait_result)
            reason = str(wait_result.get("reason", "unknown")).lower()
            if wait_result.get("ended") is not True or reason != "exit":
                raise DelegationError(
                    f"Herdr terminal {address} did not finish its headless command."
                )

            read_result = session.call(
                "terminal.read",
                {
                    "caller": address,
                    "terminal": address,
                    "lines": self.read_lines,
                },
            )
            self._validate_read_result(address, read_result)
            output = read_result["text"]
            if not output.strip():
                raise DelegationError(f"Herdr terminal {address} returned empty output.")
            return output
        except DelegationError as exc:
            raise DelegationError(
                f"{exc} Terminal {address} remains available; "
                "inspect it with `hc attach`."
            ) from exc
        finally:
            try:
                prompt_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _write_prompt_file(self, prompt: str) -> Path:
        directory = Path.cwd() / ".poseidon" / "tmp"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            prompt_path = directory / f"{uuid.uuid4().hex}.prompt.md"
            prompt_path.write_text(prompt, encoding="utf-8")
        except OSError as exc:
            raise DelegationError(f"Could not write the prompt file: {exc}") from exc
        return prompt_path

    def _headless_command_line(self, prompt_path: Path, cli_type: str) -> str:
        args = {
            "claude-code": ["claude", "-p", "--output-format", "text"],
            "codex": ["codex", "exec", "-"],
            "opencode": ["opencode", "run"],
        }[cli_type].copy()
        command_parts = [subprocess.list2cmdline(args)]
        if self.agent_model:
            command_parts.append(f'--model "{self.agent_model}"')
        command_parts.extend(self.agent_args)
        command = " ".join(command_parts)
        return f"{command} < {subprocess.list2cmdline([str(prompt_path)])}"

    def _execute_headless(
        self, session: _HerdrSession, prompt: str, cli_type: str
    ) -> str:
        argv_by_agent = {
            "claude-code": ["claude", "-p", "--output-format", "text"],
            "codex": ["codex", "exec", "-"],
            "opencode": ["opencode", "run", "--format", "json"],
        }
        result = session.call(
            "machine.exec",
            {
                "argv": argv_by_agent[cli_type],
                "input": base64.b64encode(prompt.encode("utf-8")).decode("ascii"),
                "cwd": str(Path.cwd()),
                "timeout": min(self.wait_timeout_seconds, 600),
            },
        )
        if result.get("timed_out"):
            raise DelegationError("Headless Herdr execution timed out.")
        if result.get("truncated"):
            raise DelegationError("Headless Herdr output was truncated.")

        code = result.get("code")
        if code not in (None, 0):
            details = self._decode_base64(result.get("stderr", "")).strip()
            raise DelegationError(
                f"Headless agent exited with code {code}: {details or 'No details.'}"
            )

        output = self._decode_base64(result.get("stdout", ""))
        if not output.strip():
            raise DelegationError("Headless Herdr returned empty output.")
        return output

    def _print_wait_feedback(self, address: str) -> None:
        self.console.print(
            f"⏳ Agente lanzado en terminal {address}. Esperando a que termine...",
            style="cyan",
        )
        self.console.print(
            "💡 Si el agente se queda pidiendo permisos, abre otra terminal y usa: "
            f"hc attach {address}",
            style="yellow",
        )

    def _print_wait_result(self, wait_result: Mapping[str, Any]) -> None:
        reason = wait_result.get("reason", "unknown")
        status = wait_result.get("status") or "unreported"
        ended = wait_result.get("ended", False)
        self.console.print(
            f"Herdr wait result: reason={reason}, status={status}, ended={ended}",
            style="dim",
        )

    @staticmethod
    def _validate_wait_result(address: str, wait_result: Mapping[str, Any]) -> None:
        reason = str(wait_result.get("reason", "unknown")).lower()
        ended = wait_result.get("ended") is True
        status = wait_result.get("status") or "unreported"
        if reason == "message":
            sender = wait_result.get("from") or "unknown sender"
            raise DelegationError(
                f"Herdr terminal {address} received a message from {sender}; "
                f"inspect it with `hc attach {address}`."
            )
        if reason == "not_started":
            raise DelegationError(
                f"Herdr terminal {address} did not start an agent turn."
            )
        if reason == "timeout":
            raise DelegationError(
                f"Herdr turn timed out with status '{status}'. "
                f"The agent may still be running; inspect with `hc attach {address}` "
                f"or `hc read {address}`, and stop it with `hc kill {address}`."
            )

        exit_code = wait_result.get("exit_code")
        if exit_code not in (None, 0):
            raise DelegationError(
                f"Herdr terminal {address} exited with code {exit_code}."
            )
        if not ended and reason not in {"status", "exit", "output"}:
            raise DelegationError(
                f"Herdr terminal {address} returned unexpected wait reason "
                f"'{reason}' (status: {status})."
            )

    @staticmethod
    def _validate_read_result(address: str, read_result: Mapping[str, Any]) -> None:
        why = read_result.get("why")
        if why:
            raise DelegationError(
                f"Herdr terminal {address} output is not stable: {why}."
            )
        if read_result.get("complete") is not True:
            how = read_result.get("how") or "unknown"
            raise DelegationError(
                f"Herdr terminal {address} returned incomplete output (how={how})."
            )
        if not isinstance(read_result.get("text"), str):
            raise DelegationError(
                f"Herdr terminal {address} returned non-text output."
            )

    def _timeout_for(self, method: str) -> float:
        if method == "machine.exec":
            return max(
                self.connection_timeout_seconds,
                min(self.wait_timeout_seconds + 5, 605),
            )
        if method in {"terminal.send", "terminal.wait"}:
            return max(
                self.connection_timeout_seconds,
                self.wait_timeout_seconds + 5,
            )
        return self.connection_timeout_seconds

    @staticmethod
    def _rpc_error(method: str, error: Any) -> DelegationError:
        if not isinstance(error, dict):
            raise DelegationError(
                f"Herdr {method} returned invalid error type "
                f"'{type(error).__name__}'."
            )
        message = str(error.get("message", "Unknown JSON-RPC error"))
        data = error.get("data")
        hint = data.get("hint") if isinstance(data, dict) else None
        suffix = f" {hint}" if hint else ""
        return DelegationError(f"Herdr {method} failed: {message}.{suffix}".rstrip())

    @staticmethod
    def _decode_base64(value: Any) -> str:
        if not isinstance(value, str):
            raise DelegationError("Herdr returned invalid base64 output.")
        try:
            return base64.b64decode(value).decode("utf-8", errors="replace")
        except (ValueError, TypeError) as exc:
            raise DelegationError("Herdr returned malformed base64 output.") from exc
