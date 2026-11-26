# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = (
    collect_data_files("litellm")
    + collect_data_files("textual")
    + collect_data_files("questionary")
)
hiddenimports = (
    collect_submodules("litellm")
    + collect_submodules("textual")
    + collect_submodules("questionary")
    + [
        "yaml",
        "dotenv",
        "rich.markdown",
        "rich.table",
        "rich.markup",
        "rich.console",
        "rich.text",
        "rich.style",
        "rich.theme",
        "textual.widgets._text_area",
    ]
)

a = Analysis(
    ["src/poseidon/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime_hook_litellm.py"],
    excludes=[
        "textual_dev",
        "pytest",
        "black",
        "ruff",
        "sphinx",
        "mypy",
        "pyflakes",
        "pycodestyle",
        "bandit",
        "flake8",
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="poseidon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)