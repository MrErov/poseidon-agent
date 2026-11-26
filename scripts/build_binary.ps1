$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv sync --extra binary
    uv run pyinstaller --clean --noconfirm build.spec
    Write-Host ""
    Write-Host "Binary: $root\dist\poseidon.exe"
}
finally {
    Pop-Location
}
