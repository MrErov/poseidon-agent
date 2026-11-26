# Repository Overview

> Fixture ejecutable para el flujo E2E de Poseidón; materializa una API FastAPI mínima en `examples/health_api/` para la historia US-002.

## Stack
- Language(s): Python 3.12
- Frameworks: FastAPI (fixture mínimo; el endpoint `/health` lo añade US-002)
- Package manager: uv

## Bounded contexts
1. `api` — `docs/context/api.md` — API HTTP JSON consumida por Kubernetes.

## Global commands
- Install: `uv sync --extra dev`
- Test: `.venv\Scripts\python.exe -m pytest`
- Lint: `.venv\Scripts\python.exe -m ruff check .`

## Phase 0 status
- [x] Reconnaissance
- [x] Contexts detected (1)
- [x] Per-context documentation
- [x] Dependency map
- [x] Risk register (no aplica al fixture sin implementación)

## Handoff → Phase 1
- `docs/context/00-overview.md`
- `docs/context/01-dependency-map.md`
- `docs/context/api.md`
