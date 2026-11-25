# Changelog

All notable changes to Poseidon Agent will be documented in this file.

## [3.4.0] - 2026-11-24
### Added
- **VHS demo script** (`demo.tape`) to regenerate `docs/assets/tui-demo.gif` with a dark Dracula theme.
- **Keel Nav README** (`docs/keel-nav/README.md`) with the "Two Ways to Sail" comparison and a cross-link to Poseidón.

### Changed
- Redesigned product-style `README.md`: hero with version/tests/license badges, demo GIF, "Why Poseidon?" comparison table and an architecture diagram centered on `CLI/TUI → SpecStateMachine → ExecutionEngine (API/Herdr)`.

## [3.3.0] - 2026-11-24
### Refactored
- **W1 God Object**: Split `PhaseRunner` into three cohesive classes:
  - `SpecStateMachine`: Frontmatter I/O, state transitions, gate validation.
  - `PromptBuilder`: Hot memory construction, context injection, Graphify integration.
  - `ExecutionEngine`: LiteLLM API calls, local CLI delegation, Herdr integration.
  - `PhaseRunner` now acts as a thin orchestrator coordinating the three components.
- **W2 Config Validation**: Added `ConfigValidationError` with strict type checking for all config fields (executor, runtime, model, herdr settings). Rejects `bool("false")` → `True` bug; requires explicit `true`/`false`.
- **W3 Atomic Persistence**: All writes (artifacts, spec updates) use temp file + `os.replace()` for crash safety. No more truncated specs on power loss.
- **New Public API**: `SpecStateMachine`, `PromptBuilder`, `ExecutionEngine`, `ConfigValidationError` exported from package root.

### Fixed
- **GateError Type**: `validate_gate()` now raises `GateError` (not `InputValidationError`) for backward compatibility.
- **Tests**: Updated all patches to target new module locations (`execution_engine.litellm`, `prompt_builder.fetch_graph_context`).

### Added
- Strict herdr config validation (numeric ranges, type coercion).
- Atomic write helper in `SpecStateMachine._atomic_write()`.
- Tests for atomic persistence, config validation errors, and new class boundaries.

## [3.1.0] - 2026-11-24
### Fixed
- **B1 Gatekeeper Bypass**: Gatekeeper now validates using resolved `phase_kind` instead of raw phase string. Aliases like `03`, ` 2`, `tdd` are now properly blocked for draft specs.
- **B1 Illegal State Transitions**: Added `SpecStatus` enum and explicit transition table (`DRAFT → AUDITED → APPROVED/OBSERVED → CERTIFIED`). Transitions like `DRAFT → CERTIFIED` now raise `IllegalTransitionError`.
- **B2 Spec Contract**: Metadata (`status`, `goldfish_audit`, `drift_report`) moved to frontmatter (line 1) in `templates/spec.template.md`. Artifacts now strip Markdown fences before saving.
- **B3 Verdict Injection**: Added `_extract_strict_verdict()` that parses **only** the frontmatter of generated reports using `yaml.safe_load`. Regex search over full text is removed; injected verdicts in prose are ignored.
- **Security**: Herdr JSON-RPC validation hardened against malformed responses (non-dict `result`/`error`).

### Added
- `SpecStatus` enum with `DRAFT`, `AUDITED`, `APPROVED`, `OBSERVED`, `CERTIFIED`.
- `IllegalTransitionError` for invalid state transitions.
- Tests for gatekeeper alias blocking and prompt injection protection.

## [1.0.0-alpha] - 2026-11-22
### Added
- Initial release of the Deterministic Execution Engine for Keel Nav.
- `PhaseRunner` with support for Phases 0 to 4.
- Cold Memory injection from `.meta-skills/` and `specs/`.
- Strict memory isolation for the Goldfish Audit (Phase 1b).
- Auto-Save for all artifacts (`spec`, `audit`, `observation`, `drift`).
- State Machine and Gatekeeper (blocks Phase 2 if spec is not `audited`).
- LiteLLM integration for API execution (e.g., NVIDIA NIM).
- Delegation Engine for local CLI execution (Claude Code, Codex, OpenCode).
- Graphify MCP integration for dynamic dependency graph injection.
