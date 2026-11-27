"""Single source of truth for the Poseidon version.

The version is embedded as a literal so frozen binaries (PyInstaller) can report
it without relying on installed package metadata.
"""

from __future__ import annotations

__version__ = "4.1.2"


def get_version() -> str:
    """Return the current Poseidon version string."""
    return __version__
