"""Persistent and headless agent delegation through herdr-core JSON-RPC."""

from __future__ import annotations

import atexit
import base64
import json
import queue
import re
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from poseidon.console import configure_utf8_output
from poseidon.exceptions import DelegationError
from poseidon.types import _split_frontmatter

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
        self.delegator._debug_log("→", payload)
        timeout = self.delegator._timeout_for(method)
        try:
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            self._check_process_exit(method)
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
            self.delegator._debug_log("←", item)
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
        auto_approve: bool = True,
        debug: bool = False,
        total_timeout_seconds: float = 3600.0,
        progress_interval_seconds: float = 30.0,
        phase_timeouts: Mapping[str, float] | None = None,
    ) -> None:
        if wait_timeout_seconds <= 0 or connection_timeout_seconds <= 0:
            raise ValueError("Herdr timeouts must be greater than zero")
        if read_lines < 0:
            raise ValueError("read_lines cannot be negative")
        if total_timeout_seconds <= 0 or progress_interval_seconds <= 0:
            raise ValueError("Total and progress timeouts must be greater than zero")
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
        self.auto_approve = auto_approve
        self.debug = debug
        self.total_timeout_seconds = float(total_timeout_seconds)
        self.progress_interval_seconds = float(progress_interval_seconds)
        self.phase_timeouts = dict(phase_timeouts or {})
        self._cleanup_stale_prompts()
        atexit.register(self._cleanup_stale_prompts)
        self.last_artifact_path: Path | None = None
        self.last_findings: dict[str, Any] = {}
        self.audit_round: int | None = None
        self.phase_kind: str | None = None
        self.role: str | None = None
        self._request_id = 0

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None = None,
        debug: bool = False,
    ) -> HerdrDelegator:
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
            auto_approve=bool(values.get("auto_approve", True)),
            debug=debug,
            total_timeout_seconds=float(values.get("total_timeout_seconds", 3600)),
            progress_interval_seconds=float(values.get("progress_interval_seconds", 30)),
            phase_timeouts=dict(values.get("phase_timeouts", {}) or {}),
        )

    def execute(
        self,
        prompt: str,
        cli_type: str,
        phase_kind: str | None = None,
        artifact_path: Path | None = None,
    ) -> str:
        """Execute one prompt using a single JSON-RPC connection."""
        normalized_cli = cli_type.strip().lower()
        if normalized_cli not in self._AGENTS:
            supported = ", ".join(sorted(self._AGENTS))
            raise DelegationError(
                f"Unsupported Herdr agent '{cli_type}'. Options: {supported}."
            )
        if not prompt.strip():
            raise DelegationError("Cannot send an empty prompt to Herdr.")

        self.phase_kind = phase_kind
        self.last_artifact_path = None
        with _HerdrSession(self) as session:
            if phase_kind:
                existing = self._find_live_terminal(session)
                if existing:
                    self._debug_terminal(existing)
                    self.console.print(
                        f"⏳ Reutilizando terminal {existing}.",
                        style="cyan",
                        markup=False,
                    )
                    return self._finish_from_existing_terminal(
                        session, existing, artifact_path
                    )
            if self.mode == "headless":
                return self._execute_headless(session, prompt, normalized_cli, artifact_path)
            if self.launch == "headless_in_terminal":
                return self._execute_headless_terminal(
                    session, prompt, normalized_cli, artifact_path
                )
            return self._execute_persistent(session, prompt, normalized_cli, artifact_path)

    def _debug_log(self, direction: str, payload: str) -> None:
        if self.debug:
            self.console.print(
                f"[herdr-rpc {direction}] {payload.strip()}",
                style="dim",
                markup=False,
            )

    def _debug_terminal(self, address: str) -> None:
        if self.debug:
            self.console.print(f"🐛 Herdr terminal: {address}", style="cyan", markup=False)
            self.console.print(
                f"Open another terminal and run: hc attach {address} "
                "to see what is happening",
                style="yellow",
                markup=False,
            )

    def _wait_for_turn(
        self,
        session: _HerdrSession,
        address: str,
        initial_wait_result: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        deadline = time.monotonic() + self._total_timeout_for_phase()
        next_progress = time.monotonic()
        wait_result = initial_wait_result
        while True:
            if wait_result is None:
                wait_result = session.call(
                    "terminal.wait",
                    {
                        "caller": address,
                        "terminal": address,
                        "timeout": self.wait_timeout_seconds,
                    },
                )
            if wait_result.get("reason") != "timeout":
                return wait_result
            now = time.monotonic()
            if now >= deadline:
                raise DelegationError(self._resume_message(address, deadline))
            if now >= next_progress:
                try:
                    progress = session.call(
                        "terminal.read", {"terminal": address, "lines": 5}
                    )
                    self._print_progress(address, progress.get("text", ""))
                except DelegationError:
                    pass
                next_progress = now + self.progress_interval_seconds
            wait_result = session.call(
                "terminal.wait",
                {
                    "caller": address,
                    "terminal": address,
                    "timeout": self.wait_timeout_seconds,
                },
            )

    def _total_timeout_for_phase(self) -> float:
        aliases = {
            "context": "0", "spec": "1a", "goldfish": "1b",
            "tdd": "2", "odd": "3", "drift": "4",
        }
        phase = self.phase_kind
        if phase in self.phase_timeouts:
            return float(self.phase_timeouts[phase])
        alias = aliases.get(phase or "", phase)
        return float(self.phase_timeouts.get(alias, self.total_timeout_seconds))

    def _resume_message(self, address: str, deadline: float) -> str:
        phase = self.phase_kind or "<phase>"
        command = f"poseidon run --phase {phase}"
        if self.role:
            command += f" --role {self.role}"
        command += f" --resume {address}"
        return (
            f"Herdr turn did not finish before {deadline:.0f}s. "
            f"Progress is not lost: resume with '{command}'."
        )

    def _print_progress(self, address: str, text: str) -> None:
        last_line = self._last_meaningful_line(text)
        self.console.print(
            f"⏳ {address} sigue trabajando: {last_line}",
            style="dim",
            markup=False,
        )

    @staticmethod
    def _last_meaningful_line(text: str) -> str:
        for line in reversed(text.splitlines()):
            clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line).strip()
            if clean and not clean.startswith("build ·"):
                return clean
        return "sin nueva salida"

    def _read_owned_artifact(
        self, artifact_path: Path, wait_result: Mapping[str, Any] | None = None
    ) -> str:
        expected = Path(artifact_path)
        candidates = [expected, *self._find_artifact_candidates(expected)]
        for path in candidates:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                self._validate_artifact_content(path, content)
            except DelegationError:
                continue
            self.last_artifact_path = path
            return content
        raise DelegationError(
            f"The agent did not write the expected report at {expected}."
        )

    def _find_artifact_candidates(self, expected: Path) -> list[Path]:
        name = expected.name
        if ".audit." in name:
            prefix = name.split(".audit.", 1)[0] + ".audit."
        elif ".drift." in name:
            prefix = name.split(".drift.", 1)[0] + ".drift."
        elif ".observation." in name:
            prefix = name.split(".observation.", 1)[0] + ".observation."
        elif ".spec." in name:
            prefix = name.split(".spec.", 1)[0] + ".spec."
        else:
            prefix = name
        candidates = [
            path
            for path in expected.parent.glob(f"{prefix}*.md")
            if path.is_file() and path != expected
        ]
        return sorted(
            candidates,
            key=lambda path: (self._round_for_path(path), path.stat().st_mtime),
            reverse=True,
        )

    @staticmethod
    def _round_for_path(path: Path) -> int:
        match = re.search(r"\.(?:audit|drift)\.(\d+)\.md$", path.name)
        return int(match.group(1)) if match else -1

    def _validate_artifact_content(self, path: Path, content: str) -> None:
        parts = _split_frontmatter(content)
        if parts is None:
            raise DelegationError(f"Artifact {path} has no frontmatter.")
        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            raise DelegationError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(metadata, dict):
            raise DelegationError(f"Artifact {path} has invalid metadata.")
        if self.phase_kind in {"goldfish", "drift"}:
            verdict = metadata.get("effective_verdict")
            if not isinstance(verdict, str) or not verdict.strip():
                raise DelegationError(
                    f"Artifact {path} is missing frontmatter effective_verdict."
                )
            if self.phase_kind == "goldfish":
                expected_round = self._round_for_path(path)
                if metadata.get("audit_round") != expected_round:
                    raise DelegationError(
                        f"Artifact {path} has incoherent audit_round."
                    )
                self.audit_round = expected_round
            self.last_findings = {
                key: metadata.get(key)
                for key in ("findings_blocking", "findings_warning", "findings_info")
            }

    def resume(self, terminal: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", terminal):
            raise DelegationError(f"Invalid Herdr terminal id: {terminal}")
        self.last_artifact_path = None
        with _HerdrSession(self) as session:
            return self._finish_from_existing_terminal(session, terminal, None)

    def _find_live_terminal(self, session: _HerdrSession) -> str | None:
        result = session.call("terminal.list", {})
        terminals = result.get("terminals", [])
        if not isinstance(terminals, list):
            return None
        prefix = self.name_prefix[:15]
        candidates = [
            item
            for item in terminals
            if isinstance(item, dict)
            and item.get("state") == "live"
            and str(item.get("name", "")).startswith(prefix)
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item.get("created_ms", 0) or 0)
        return best.get("address")

    def _finish_from_existing_terminal(
        self,
        session: _HerdrSession,
        address: str,
        artifact_path: Path | None,
    ) -> str:
        wait_result = self._wait_for_turn(session, address)
        self._print_wait_result(wait_result)
        self._cleanup_prompt_for_terminal(session, address)
        self._validate_wait_result(address, wait_result)
        read_result = session.call(
            "terminal.read",
            {"caller": address, "terminal": address, "lines": self.read_lines},
        )
        self._validate_read_result(address, read_result)
        if artifact_path is not None:
            return self._read_owned_artifact(artifact_path, wait_result)
        output = read_result["text"]
        if not output.strip():
            raise DelegationError(f"Herdr terminal {address} returned empty output.")
        return output

    def _cleanup_prompt_file(self, path: Path) -> None:
        last_error: OSError | None = None
        for _ in range(5):
            try:
                path.unlink(missing_ok=True)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(1.0)
        if last_error is not None:
            self.console.print(
                f"⚠️ Could not delete prompt file {path}; "
                f"it will be retried on next startup: {last_error}",
                style="yellow",
                markup=False,
            )

    def _cleanup_stale_prompts(self) -> None:
        directory = Path.cwd() / ".poseidon" / "tmp"
        if not directory.is_dir():
            return
        now = time.time()
        for path in directory.glob("*.prompt.md"):
            try:
                if now - path.stat().st_mtime > 7200:
                    self._cleanup_prompt_file(path)
            except OSError:
                self._cleanup_prompt_file(path)

    def _execute_persistent(
        self,
        session: _HerdrSession,
        prompt: str,
        cli_type: str,
        artifact_path: Path | None = None,
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

        self._debug_terminal(address)
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
            wait_result = self._wait_for_turn(
                session, address, send_result.get("wait")
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
            if artifact_path is not None:
                return self._read_owned_artifact(artifact_path, wait_result)
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
        self,
        session: _HerdrSession,
        prompt: str,
        cli_type: str,
        artifact_path: Path | None = None,
    ) -> str:
        prompt_path = self._write_prompt_file(prompt)
        address = "unknown"
        preserve_prompt = False
        try:
            self._debug_log("→", self._headless_command_line(prompt_path, cli_type))
            run_result = session.call(
                "terminal.run",
                {
                    "line": self._headless_command_line(prompt_path, cli_type),
                    "name": f"{self.name_prefix[:15]}-{prompt_path.stem[:15]}",
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

            self._debug_terminal(address)
            self._print_wait_feedback(address)
            wait_result = self._wait_for_turn(session, address)
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
            if artifact_path is not None:
                return self._read_owned_artifact(artifact_path, wait_result)
            output = read_result["text"]
            if not output.strip():
                raise DelegationError(f"Herdr terminal {address} returned empty output.")
            return output
        except DelegationError as exc:
            if "Progress is not lost" in str(exc):
                preserve_prompt = True
                self.console.print(
                    f"Prompt retained for resume: {prompt_path}",
                    style="yellow",
                    markup=False,
                )
            raise DelegationError(
                f"{exc} Terminal {address} remains available; "
                "inspect it with `hc attach`."
            ) from exc
        finally:
            if not preserve_prompt:
                self._cleanup_prompt_file(prompt_path)

    def _cleanup_prompt_for_terminal(
        self, session: _HerdrSession, address: str
    ) -> None:
        directory = Path.cwd() / ".poseidon" / "tmp"
        paths = list(directory.glob("*.prompt.md"))
        if not paths:
            return
        try:
            details = session.call("terminal.get", {"terminal": address})
        except DelegationError:
            return
        name = str(details.get("name", ""))
        directory = Path.cwd() / ".poseidon" / "tmp"
        for path in directory.glob("*.prompt.md"):
            if path.stem in name:
                self._cleanup_prompt_file(path)

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
        if self.auto_approve and cli_type == "opencode":
            command_parts.append("--auto")
        command = " ".join(command_parts)
        return f"{command} < {subprocess.list2cmdline([str(prompt_path)])}"

    def _execute_headless(
        self,
        session: _HerdrSession,
        prompt: str,
        cli_type: str,
        artifact_path: Path | None = None,
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
