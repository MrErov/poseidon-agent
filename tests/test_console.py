import io
import sys

from rich.console import Console

from poseidon.herdr_delegator import HerdrDelegator


class _CP1252Stream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self._encoding = "cp1252"
        self.reconfigured: list[dict] = []

    @property
    def encoding(self) -> str:
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        self._encoding = value

    def reconfigure(self, **kwargs) -> None:
        self.reconfigured.append(kwargs)
        self.encoding = kwargs["encoding"]


def test_herdr_emoji_output_is_utf8_safe_on_windows(monkeypatch) -> None:
    stream = _CP1252Stream()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    console = Console(file=stream)
    delegator = HerdrDelegator(console=console)

    delegator._print_wait_feedback("t42")

    assert "⏳" in stream.getvalue()
    assert "💡" in stream.getvalue()
    assert stream.reconfigured
    assert stream.reconfigured[0]["encoding"] == "utf-8"
