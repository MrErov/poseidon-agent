# Changelog

All notable changes to Poseidon Agent will be documented in this file.

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
