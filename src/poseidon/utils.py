"""Utility functions for Poseidon."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


def get_working_dir() -> Path:
    """Return the actual workspace directory, handling PyInstaller frozen state.

    When running as a compiled binary (PyInstaller --onefile), ``sys.executable``
    points to the extracted executable in a temporary directory. The user's
    actual working directory is the parent of that executable, not the
    extraction directory (``sys._MEIPASS``).
    """
    if getattr(sys, "frozen", False):
        # Running as a compiled binary (.exe on Windows, binary on Unix)
        return Path(sys.executable).parent
    # Running as a Python script
    return Path.cwd()


# --- Structured JSONL Logging ---

_LOG_ENABLED = os.environ.get("POSEIDON_LOG_JSON") == "1"
_LOG_LOCK = threading.Lock()
_LOG_FILE: Path | None = None


def _get_log_file() -> Path | None:
    """Return the log file path, creating the directory if needed."""
    global _LOG_FILE
    if _LOG_FILE is not None:
        return _LOG_FILE
    if not _LOG_ENABLED:
        return None
    try:
        log_dir = get_working_dir() / ".poseidon"
        log_dir.mkdir(parents=True, exist_ok=True)
        _LOG_FILE = log_dir / "poseidon.log.jsonl"
        return _LOG_FILE
    except OSError:
        return None


def log_event(event_type: str, **data: Any) -> None:
    """Log a structured event as JSONL if POSEIDON_LOG_JSON=1.

    Args:
        event_type: Type of event (e.g., "phase_start", "llm_call", "phase_end", "error").
        **data: Additional event data to log.
    """
    if not _LOG_ENABLED:
        return
    log_file = _get_log_file()
    if log_file is None:
        return
    entry = {
        "timestamp": time.time(),
        "event": event_type,
        **data,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _LOG_LOCK:
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # Best effort, don't crash on logging failure