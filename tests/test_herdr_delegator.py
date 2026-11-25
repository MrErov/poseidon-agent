import base64
import io
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from poseidon.exceptions import DelegationError
from poseidon.herdr_delegator import HerdrDelegator


class _InspectStringIO(io.StringIO):
    def close(self) -> None:
        pass


def _rpc(result: object, request_id: int) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n"


def _process(lines: list[str], returncode: int = 0, stderr: str = "") -> Mock:
    process = Mock()
    process.stdin = _InspectStringIO()
    process.stdout = _InspectStringIO("".join(lines))
    process.stderr = _InspectStringIO(stderr)
    process.returncode = returncode
    process.poll.return_value = returncode
    process.wait.return_value = returncode
    return process


def _wait_result(
    *,
    ended: bool = False,
    reason: str = "status",
    status: str = "done",
    exit_code: int | None = 0,
    **extra: object,
) -> dict:
    return {
        "terminal": "t42",
        "ended": ended,
        "reason": reason,
        "status": status,
        "exit_code": exit_code,
        "turn": 1,
        "children": [],
        **extra,
    }


def _read_result(
    text: str = "Agent response",
    *,
    complete: bool = True,
    how: str = "history",
    why: str | None = None,
) -> dict:
    return {"text": text, "complete": complete, "how": how, "why": why}


def _persistent_process(
    wait_result: dict,
    read_result: dict | None = None,
    *,
    inline_wait: bool = True,
) -> Mock:
    read_result = read_result or _read_result()
    lines = [
        _rpc({"address": "t42"}, 1),
        _rpc(
            {
                "turn": 1,
                "started": True,
                "status": "working",
                "wait": wait_result if inline_wait else None,
            },
            2,
        ),
    ]
    if not inline_wait:
        lines.append(_rpc(wait_result, 3))
    lines.append(_rpc(read_result, 4 if not inline_wait else 3))
    return _process(lines)


def _requests(process: Mock) -> list[dict]:
    return [json.loads(line) for line in process.stdin.getvalue().splitlines()]


def test_persistent_send_wait_uses_one_session_and_agent_turn() -> None:
    process = _persistent_process(
        _wait_result(ended=False, reason="status", status="done"),
        _read_result("## Completed"),
    )
    console = Mock()
    delegator = HerdrDelegator(console=console, launch="interactive")

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process) as popen:
        result = delegator.execute("large prompt", "claude-code")

    assert result == "## Completed"
    popen.assert_called_once()
    requests = _requests(process)
    assert [request["method"] for request in requests] == [
        "terminal.run",
        "terminal.send",
        "terminal.read",
    ]
    assert requests[1]["params"]["text"] == "large prompt"
    assert requests[1]["params"]["wait"] is True
    assert requests[1]["params"]["caller"] == "t42"
    assert "caller" not in requests[0]["params"]
    assert requests[2]["params"]["caller"] == "t42"
    assert console.print.call_count == 3
    assert "reason=status" in console.print.call_args_list[2].args[0]


def test_exit_reason_is_accepted() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit", status=None),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        assert HerdrDelegator(launch="interactive").execute("prompt", "codex") == "Agent response"


def test_fallback_wait_uses_same_caller() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit"),
        inline_wait=False,
    )
    delegator = HerdrDelegator(launch="interactive")

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        assert delegator.execute("prompt", "claude-code") == "Agent response"

    requests = _requests(process)
    assert [request["method"] for request in requests][-2:] == [
        "terminal.wait",
        "terminal.read",
    ]
    assert requests[2]["params"]["caller"] == "t42"


def test_wait_timeout_has_recovery_hints() -> None:
    process = _persistent_process(
        _wait_result(ended=False, reason="timeout", status="working"),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="timed out.*hc attach.*hc read.*hc kill"):
            HerdrDelegator(launch="interactive").execute("prompt", "opencode")

    methods = [request["method"] for request in _requests(process)]
    assert methods == ["terminal.run", "terminal.send"]


def test_wait_message_includes_sender() -> None:
    process = _persistent_process(
        _wait_result(ended=False, reason="message", status="working", **{"from": "t9"}),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="message from t9"):
            HerdrDelegator(launch="interactive").execute("prompt", "opencode")


def test_not_started_is_controlled_error() -> None:
    process = _persistent_process(
        _wait_result(ended=False, reason="not_started", status=None),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="did not start an agent turn"):
            HerdrDelegator(launch="interactive").execute("prompt", "opencode")


def test_incomplete_read_is_rejected() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit"),
        _read_result("partial", complete=False, how="history"),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="incomplete output"):
            HerdrDelegator(launch="interactive").execute("prompt", "opencode")


def test_stitched_complete_read_is_normal() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit"),
        _read_result("full screen response", complete=True, how="stitched"),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        result = HerdrDelegator(launch="interactive").execute(
            "prompt", "opencode"
        )
        assert result == "full screen response"


def test_read_working_reason_is_rejected() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit"),
        _read_result("unfinished", complete=True, how="screen", why="working"),
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="not stable: working"):
            HerdrDelegator(launch="interactive").execute("prompt", "opencode")


def test_notifications_and_non_json_lines_are_ignored() -> None:
    process = _process([
        "not json\n",
        json.dumps({"jsonrpc": "2.0", "method": "event", "params": {}}) + "\n",
        _rpc({"address": "t42"}, 1),
        _rpc({"wait": _wait_result(ended=True, reason="exit")}, 2),
        _rpc(_read_result("ok"), 3),
    ])

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        assert HerdrDelegator(launch="interactive").execute("prompt", "codex") == "ok"


def test_headless_exec_decodes_base64_output() -> None:
    stdout = base64.b64encode(b"headless result").decode("ascii")
    process = _process([
        _rpc(
            {
                "code": 0,
                "stdout": stdout,
                "stderr": "",
                "timed_out": False,
                "truncated": False,
                "ms": 42,
            },
            1,
        )
    ])
    delegator = HerdrDelegator(mode="headless", wait_timeout_seconds=900)

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process) as popen:
        assert delegator.execute("headless prompt", "opencode") == "headless result"

    popen.assert_called_once()
    request = _requests(process)[0]
    assert request["method"] == "machine.exec"
    assert base64.b64decode(request["params"]["input"]).decode() == "headless prompt"
    assert request["params"]["timeout"] == 600
    assert request["params"]["argv"] == ["opencode", "run", "--format", "json"]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        ({"timed_out": True, "stdout": "", "stderr": "", "code": None}, "timed out"),
        (
            {
                "timed_out": False,
                "truncated": True,
                "stdout": "",
                "stderr": "",
                "code": 0,
            },
            "truncated",
        ),
        (
            {
                "timed_out": False,
                "truncated": False,
                "stdout": "",
                "stderr": "ZmluZA==",
                "code": 2,
            },
            "code 2",
        ),
    ],
)
def test_headless_rejects_bad_results(result: dict, message: str) -> None:
    process = _process([_rpc(result, 1)])

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match=message):
            HerdrDelegator(mode="headless").execute("prompt", "codex")


def test_missing_executable_is_controlled() -> None:
    with patch(
        "poseidon.herdr_delegator.subprocess.Popen",
        side_effect=FileNotFoundError("hc not found"),
    ):
        with pytest.raises(DelegationError, match="not installed"):
            HerdrDelegator(launch="interactive").execute("prompt", "claude-code")


def test_json_rpc_error_is_controlled() -> None:
    error = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32000,
                "message": "connection failed",
                "data": {"kind": "unavailable", "hint": "start the core"},
            },
        }
    ) + "\n"
    process = _process([error])

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="connection failed.*start the core"):
            HerdrDelegator(launch="interactive").execute("prompt", "claude-code")


def test_non_dict_error_is_rejected() -> None:
    process = _process([json.dumps({"jsonrpc": "2.0", "id": 1, "error": "bad"}) + "\n"])

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="invalid error type"):
            HerdrDelegator(launch="interactive").execute("prompt", "claude-code")


def test_non_dict_result_is_rejected() -> None:
    process = _process([json.dumps({"jsonrpc": "2.0", "id": 1, "result": "bad"}) + "\n"])

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="invalid result type"):
            HerdrDelegator(launch="interactive").execute("prompt", "claude-code")


def test_transport_timeout_kills_only_client() -> None:
    class SlowStream:
        def __iter__(self):
            return self

        def __next__(self):
            time.sleep(0.05)
            raise StopIteration

    process = Mock()
    process.stdin = _InspectStringIO()
    process.stdout = SlowStream()
    process.stderr = _InspectStringIO()
    process.wait.side_effect = subprocess.TimeoutExpired(cmd="hc", timeout=1)
    delegator = HerdrDelegator(connection_timeout_seconds=0.001)

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="exceeded 0.001 seconds"):
            delegator.execute("prompt", "claude-code")

    process.terminate.assert_called_once()


def test_from_settings_uses_mode_and_900_second_default() -> None:
    delegator = HerdrDelegator.from_settings({"mode": "headless"})

    assert delegator.mode == "headless"
    assert delegator.wait_timeout_seconds == 900
    assert delegator.launch == "headless_in_terminal"


def _headless_terminal_process(
    wait_result: dict | None = None,
    read_result: dict | None = None,
) -> Mock:
    wait_result = wait_result or _wait_result(
        ended=True, reason="exit", status=None, exit_code=0
    )
    read_result = read_result or _read_result("PONG")
    return _process(
        [
            _rpc({"address": "t42"}, 1),
            _rpc(wait_result, 2),
            _rpc(read_result, 3),
        ]
    )


def _prompt_path(process: Mock) -> Path:
    from pathlib import Path as PathType

    line = _requests(process)[0]["params"]["line"]
    return PathType(line.split(" < ", 1)[1].strip('"'))


def test_headless_terminal_uses_run_wait_read_and_cleans_prompt(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process()

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process) as popen:
        assert HerdrDelegator().execute("exact prompt", "opencode") == "PONG"

    popen.assert_called_once()
    requests = _requests(process)
    assert [request["method"] for request in requests] == [
        "terminal.run",
        "terminal.wait",
        "terminal.read",
    ]
    assert requests[0]["params"]["line"].startswith("opencode run < ")
    assert not _prompt_path(process).exists()
    monkeypatch.undo()


def test_headless_terminal_interpolates_model_and_args(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process()
    delegator = HerdrDelegator(
        agent_model="nvidia/test-model",
        agent_args=["--format", "json"],
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        delegator.execute("THE_ACTUAL_PROMPT_CONTENT", "opencode")

    line = _requests(process)[0]["params"]["line"]
    assert '--model "nvidia/test-model"' in line
    assert "--format json" in line
    assert "THE_ACTUAL_PROMPT_CONTENT" not in line
    monkeypatch.undo()


def test_prompt_file_contains_exact_text_before_cleanup(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    delegator = HerdrDelegator()
    prompt_path = delegator._write_prompt_file("hola\nmundo")

    assert prompt_path.read_text(encoding="utf-8") == "hola\nmundo"
    assert not list(prompt_path.parent.glob("*.other"))
    prompt_path.unlink()
    monkeypatch.undo()


def test_prompt_file_is_deleted_on_wait_timeout(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process(
        _wait_result(ended=False, reason="timeout", status="working")
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="timed out"):
            HerdrDelegator().execute("prompt", "opencode")

    assert not _prompt_path(process).exists()
    monkeypatch.undo()


def test_headless_terminal_nonzero_exit_is_error(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process(
        _wait_result(ended=True, reason="exit", status=None, exit_code=7)
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="code 7"):
            HerdrDelegator().execute("prompt", "opencode")

    assert not _prompt_path(process).exists()
    monkeypatch.undo()


def test_headless_command_quotes_paths_with_spaces(tmp_path: Path) -> None:
    project = tmp_path / "space project"
    project.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(project)
    process = _headless_terminal_process()

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        HerdrDelegator().execute("prompt", "opencode")

    line = _requests(process)[0]["params"]["line"]
    assert '< "' in line
    assert str(project) in line
    monkeypatch.undo()


def test_headless_read_why_is_rejected(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process(
        read_result=_read_result("bad", complete=True, why="working")
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="not stable"):
            HerdrDelegator().execute("prompt", "opencode")

    monkeypatch.undo()


def test_headless_incomplete_read_is_rejected(tmp_path: Path) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    process = _headless_terminal_process(
        read_result=_read_result("partial", complete=False)
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        with pytest.raises(DelegationError, match="incomplete output"):
            HerdrDelegator().execute("prompt", "opencode")

    assert not _prompt_path(process).exists()
    monkeypatch.undo()


def test_interactive_send_uses_real_terminal_address() -> None:
    process = _persistent_process(_wait_result(ended=True, reason="exit"))

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        HerdrDelegator(launch="interactive").execute("prompt", "claude-code")

    requests = _requests(process)
    assert "caller" not in requests[0]["params"]
    assert requests[1]["params"]["caller"] == "t42"
    assert requests[2]["params"]["caller"] == "t42"


def test_interactive_fallback_wait_uses_real_terminal_address() -> None:
    process = _persistent_process(
        _wait_result(ended=True, reason="exit"), inline_wait=False
    )

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=process):
        HerdrDelegator(launch="interactive").execute("prompt", "claude-code")

    requests = _requests(process)
    assert requests[2]["params"]["caller"] == "t42"
    assert requests[3]["params"]["caller"] == "t42"
