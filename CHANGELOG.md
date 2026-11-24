# Changelog

All notable changes to Poseidon Agent will be documented in this file.

## [3.2.0] - 2026-11-24
### Fixed
- **B4 TUI Improvements**: Added `Input` widgets for Spec Path and Context Path. Phase execution now reads these inputs and passes them to `PhaseRunner.run()`. Herdr console output now routes through TUI's `_MessageText` adapter (no more screen corruption). Removed duplicate output rendering.
- **B5 Herdr JSON-RPC Hardening**: Strict validation that `result` and `error` are dicts before field access. Added `_get_str_field()` and `_get_bool_field()` helpers. `terminal.read` now verifies `complete=true` to detect truncated reads.
- **B6 Timeouts & Cancellation**: LiteLLM `completion()` now uses 300s timeout. Added `Ctrl+X` binding to cancel running worker (and Herdr terminal if applicable).

### Added
- TUI: Spec/Context path inputs, cancellation support, non-markup RichLog.
- Herdr: Strict JSON-RPC response validation, incomplete-read detection.
- Core: 300s timeout on LiteLLM calls.
- Tests for Herdr non-dict result/error, incomplete reads, empty address/text.

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
