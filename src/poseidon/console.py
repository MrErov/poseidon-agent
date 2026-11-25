"""Console encoding helpers shared by CLI and library consumers."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any


def configure_utf8_output(streams: Iterable[Any] | None = None) -> None:
    """Upgrade legacy Windows output streams to UTF-8 when reconfiguration exists."""
    if sys.platform != "win32":
        return

    targets = (sys.stdout, sys.stderr) if streams is None else streams
    for stream in targets:
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("_", "-")
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding not in {"utf-8", "utf8"} and callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
