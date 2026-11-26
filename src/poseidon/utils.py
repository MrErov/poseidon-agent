"""Utility functions for Poseidon."""

from __future__ import annotations

import sys
from pathlib import Path


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