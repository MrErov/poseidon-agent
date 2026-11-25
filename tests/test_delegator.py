import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from poseidon.delegator import DelegationError, LocalCLIDelegator


@pytest.mark.parametrize(
    ("cli_type", "expected_command"),
    [
        ("codex", ["codex", "exec", "-"]),
        ("opencode", ["opencode", "run"]),
    ],
)
def test_delegator_passes_prompt_via_stdin(cli_type: str, expected_command: list[str]) -> None:
    delegator = LocalCLIDelegator(executables={cli_type: expected_command[0]})
    completed = SimpleNamespace(returncode=0, stdout="resultado", stderr="")

    with patch("poseidon.delegator.subprocess.run", return_value=completed) as run:
        assert delegator.execute("prompt de prueba", cli_type) == "resultado"

    command = run.call_args.args[0]
    assert command == expected_command
    assert "prompt de prueba" not in command
    assert run.call_args.kwargs["input"] == "prompt de prueba"
    assert "stdin" not in run.call_args.kwargs
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize(
    ("cli_type", "expected_command"),
    [
        ("opencode", ["opencode", "run", "--model", "nvidia/test"]),
        (
            "claude-code",
            ["claude", "-p", "--output-format", "text", "--model", "nvidia/test"],
        ),
        ("codex", ["codex", "exec", "-", "--model", "nvidia/test"]),
    ],
)
def test_delegator_propagates_model_to_local_executors(
    cli_type: str, expected_command: list[str]
) -> None:
    delegator = LocalCLIDelegator(executables={cli_type: expected_command[0]})
    completed = SimpleNamespace(returncode=0, stdout="resultado", stderr="")

    with patch("poseidon.delegator.subprocess.run", return_value=completed) as run:
        delegator.execute("prompt", cli_type, model="nvidia/test")

    assert run.call_args.args[0] == expected_command
    assert run.call_args.kwargs["input"] == "prompt"
    assert run.call_args.kwargs["shell"] is False


def test_delegator_preserves_executable_path_with_spaces() -> None:
    executable = r"C:\Tools\Open Code\opencode.exe"
    delegator = LocalCLIDelegator(executables={"opencode": executable})
    completed = SimpleNamespace(returncode=0, stdout="resultado", stderr="")

    with patch("poseidon.delegator.subprocess.run", return_value=completed) as run:
        delegator.execute("prompt", "opencode")

    assert run.call_args.args[0][0] == executable


def test_delegator_raises_on_nonzero_return_code() -> None:
    delegator = LocalCLIDelegator(executables={"codex": "codex"})
    completed = SimpleNamespace(returncode=2, stdout="", stderr="fallo de autenticación")

    with patch("poseidon.delegator.subprocess.run", return_value=completed):
        with pytest.raises(DelegationError, match="código 2.*autenticación"):
            delegator.execute("prompt", "codex")


def test_delegator_raises_on_timeout() -> None:
    delegator = LocalCLIDelegator(
        timeout_seconds=1,
        executables={"claude-code": "claude"},
    )

    with patch(
        "poseidon.delegator.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1),
    ):
        with pytest.raises(DelegationError, match="timeout de 1 segundos"):
            delegator.execute("prompt", "claude-code")
