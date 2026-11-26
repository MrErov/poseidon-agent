"""Runtime hook for litellm to find templates in PyInstaller frozen environment."""

import os
import sys
from pathlib import Path


def _fix_litellm_paths() -> None:
    """Ensure litellm can find its template files when frozen."""
    if not getattr(sys, "frozen", False):
        return

    # In onefile mode, sys._MEIPASS points to the extraction directory
    # where PyInstaller unpacks the bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return

    meipass_path = Path(meipass)

    # litellm looks for templates in its package directory
    # Add the extraction directory to the search path
    litellm_templates = meipass_path / "litellm" / "prompt_templates"
    if litellm_templates.is_dir():
        os.environ.setdefault("LITELLM_TEMPLATE_DIR", str(litellm_templates))

    # Also set LITELLM_CONFIG_PATH if needed
    litellm_config = meipass_path / "litellm" / "config.yaml"
    if litellm_config.is_file():
        os.environ.setdefault("LITELLM_CONFIG_PATH", str(litellm_config))


_fix_litellm_paths()