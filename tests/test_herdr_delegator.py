import json
from unittest.mock import Mock, patch

import pytest

from poseidon.delegator import DelegationError
from poseidon.herdr_delegator import HerdrDelegator


def _rpc(result: object, request_id: int = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n"


def _process(stdout: str, returncode: int = 0, stderr: str = "") -> Mock:
    process = Mock()
    process.returncode = returncode
    process.communicate.return_value = (stdout, stderr)
    return process


def test_herdr_executes_full_json_rpc_lifecycle() -> None:
    processes = [
        _process(_rpc({"address": "t42"})),
        _process(_rpc({"turn": 1}, request_id=2)),
        _process(
            _rpc(
                {
                    "terminal": "t42",
                    "ended": True,
                    "reason": "exit",
                    "exit_code": 0,
                    "turn": 1,
                    "children": [],
                },
                request_id=3,
            )
        ),
        _process(_rpc({"text": "## Result", "complete": True, "how": "history"}, request_id=4)),
    ]
    console = Mock()
    delegator = HerdrDelegator(name_prefix="poseidon-test", console=console)

    with patch("poseidon.herdr_delegator.subprocess.Popen", side_effect=processes) as popen:
        result = delegator.execute("large prompt", "claude-code")

    assert result == "## Result"
    assert popen.call_count == 4
    requests = [
        json.loads(process.communicate.call_args.kwargs["input"])
        for process in processes
    ]
    assert [request["method"] for request in requests] == [
        "terminal.run",
        "terminal.send",
        "terminal.wait",
        "terminal.read",
    ]
    assert requests[0]["params"]["argv"] == ["claude"]
    assert requests[0]["params"]["wait"] is False
    assert requests[0]["params"]["outlive_parent"] is True
    assert requests[1]["params"]["text"] == "large prompt\n"
    assert requests[3]["params"]["terminal"] == "t42"
    assert console.print.call_count == 2
    first_message = console.print.call_args_list[0]
    second_message = console.print.call_args_list[1]
    assert "t42" in first_message.args[0]
    assert first_message.kwargs["style"] == "cyan"
    assert "hc attach t42" in second_message.args[0]
    assert second_message.kwargs["style"] == "yellow"


def test_herdr_ignores_unrelated_json_rpc_messages() -> None:
    output = _rpc({"text": "ok", "complete": True, "how": "history"}, request_id=4)
    notification = json.dumps({"jsonrpc": "2.0", "method": "event", "params": {}}) + "\n"
    processes = [
        _process(_rpc({"address": "t42"})),
        _process(_rpc({"turn": 1}, request_id=2)),
        _process(_rpc({"ended": True, "exit_code": 0}, request_id=3)),
        _process(notification + output),
    ]

    with patch("poseidon.herdr_delegator.subprocess.Popen", side_effect=processes):
        assert HerdrDelegator().execute("prompt", "codex") == "ok"


def test_herdr_timeout_preserves_terminal() -> None:
    processes = [
        _process(_rpc({"address": "t42"})),
        _process(_rpc({"turn": 1}, request_id=2)),
        _process(_rpc({"terminal": "t42", "ended": False, "reason": "timeout"}, request_id=3)),
    ]

    with patch("poseidon.herdr_delegator.subprocess.Popen", side_effect=processes) as popen:
        with pytest.raises(DelegationError, match="t42.*still running"):
            HerdrDelegator().execute("prompt", "opencode")

    assert popen.call_count == 3


def test_herdr_reports_missing_executable() -> None:
    with patch(
        "poseidon.herdr_delegator.subprocess.Popen",
        side_effect=FileNotFoundError("hc not found"),
    ):
        with pytest.raises(DelegationError, match="not installed"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_reports_json_rpc_error() -> None:
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

    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=_process(error)):
        with pytest.raises(DelegationError, match="connection failed.*start the core"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_from_settings() -> None:
    delegator = HerdrDelegator.from_settings(
        {
            "executable": "/opt/herdr/hc",
            "wait_timeout_seconds": 45,
            "read_lines": 250,
            "keep": False,
            "outlive_parent": False,
            "name_prefix": "tester",
        }
    )

    assert delegator.executable == "/opt/herdr/hc"
    assert delegator.wait_timeout_seconds == 45
    assert delegator.read_lines == 250
    assert delegator.keep is False
    assert delegator.outlive_parent is False
    assert delegator.name_prefix == "tester"


def test_herdr_rejects_non_dict_result() -> None:
    """JSON-RPC result must be a dict; string/list results are rejected."""
    # terminal.run returns a string instead of an object
    bad_result = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "not-a-dict"}) + "\n"
    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=_process(bad_result)):
        with pytest.raises(DelegationError, match="invalid result"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_rejects_non_dict_error() -> None:
    """JSON-RPC error must be a dict; string errors are rejected."""
    bad_error = json.dumps({"jsonrpc": "2.0", "id": 1, "error": "just a string"}) + "\n"
    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=_process(bad_error)):
        with pytest.raises(DelegationError, match="invalid error"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_rejects_incomplete_read() -> None:
    """terminal.read with complete=false should raise DelegationError."""
    processes = [
        _process(_rpc({"address": "t42"})),
        _process(_rpc({"turn": 1}, request_id=2)),
        _process(_rpc({"ended": True, "exit_code": 0}, request_id=3)),
        # read_result with complete=False
        _process(_rpc({"text": "partial output", "complete": False}, request_id=4)),
    ]

    with patch("poseidon.herdr_delegator.subprocess.Popen", side_effect=processes):
        with pytest.raises(DelegationError, match="truncated|complete"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_rejects_empty_address() -> None:
    """terminal.run returning empty address should fail."""
    bad_result = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"address": ""}}) + "\n"
    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=_process(bad_result)):
        with pytest.raises(DelegationError, match="terminal address"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_rejects_missing_address_field() -> None:
    """terminal.run missing address field should fail."""
    bad_result = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
    with patch("poseidon.herdr_delegator.subprocess.Popen", return_value=_process(bad_result)):
        with pytest.raises(DelegationError, match="terminal address"):
            HerdrDelegator().execute("prompt", "claude-code")


def test_herdr_rejects_empty_text_output() -> None:
    """terminal.read returning empty text should fail."""
    processes = [
        _process(_rpc({"address": "t42"})),
        _process(_rpc({"turn": 1}, request_id=2)),
        _process(_rpc({"ended": True, "exit_code": 0}, request_id=3)),
        _process(_rpc({"text": "", "complete": True}, request_id=4)),
    ]

    with patch("poseidon.herdr_delegator.subprocess.Popen", side_effect=processes):
        with pytest.raises(DelegationError, match="empty output|remains available"):
            HerdrDelegator().execute("prompt", "claude-code")
