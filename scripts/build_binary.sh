#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

uv sync --extra binary
uv run pyinstaller --clean --noconfirm build.spec

printf '\nBinary: %s/dist/poseidon\n' "$root"
