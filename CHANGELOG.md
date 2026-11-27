## [Unreleased]

## [4.1.0] - 2026-11-27
### Added
- **Multi-Model Routing**: New `ModelRouter` class with `PHASE_TO_ROLE` mapping (planner/coder/reviewer) for automatic model selection per phase.
- **Config-driven Model Routing**: New `model_routing` section in `config.yaml` with `planner`, `coder`, `reviewer`, and `default` model assignments.
- **TUI Model Dropdown**: Replaced free-text model input with a `Select` dropdown populated from `model_routing`; auto-selects appropriate model when phase changes.
- **CLI Model Commands**: New `poseidon models list` and `poseidon config init` for interactive model configuration.
- **ConfigManager.get_model_routing()**: Returns `ModelRouting` object with defaults.

### Changed
- **PhaseRunner**: Now accepts `ModelRouter` / `ModelRouting` for automatic model resolution per phase (API executor only).
- **TUI**: Model input replaced with dropdown; auto-selects role-based model when phase changes.
- **Core**: Model resolution only applies to `api` executor; local executors use role config or CLI `--model`.
- **Tests**: Added `tests/test_model_router.py` with 7 tests for phase→model resolution, override, and fallback behavior.

## [4.0.0] - 2026-11-26
### Added
- **Golden Master Release**: Production-ready milestone with all core features stabilized.
- **Complete Feature Set**: Responsive TUI, Herdr delegation, MCP Registry Manager, API Session Resume, Doctor, JSONL Logging, optional `litellm`, Release Pipeline.
- **214 Tests**: Full test coverage including unit, integration, TUI layout, MCP, and session resume tests.

### Changed
- Version bump to 4.0.0 (Golden Master) — API and CLI considered stable.
- Documentation polished: README restructured with Quickstart, comprehensive usage, troubleshooting.
- All lints pass (Ruff clean), all tests pass (214), binary builds (99.9 MB).

## [3.9.0] - 2026-11-26
### Added
- **MCP Registry Manager** (`poseidon mcp`): `list` command scans OpenCode, Codex, and Claude Code configs; `sync` command copies MCP servers between agents with safe JSON/TOML merging.
- **API Session Resume**: `--resume` now works with `api` executor; Hot Memory (message history) persisted to `.poseidon/sessions/` and auto-resumed on failure/timeout.
- **Release Pipeline**: GitHub Actions workflow builds Windows (Inno Setup `.exe` installer), Linux, and macOS binaries; optional `cosign` signing; artifacts attached to GitHub Release.

### Changed
- `run` command: `--resume` now accepts API session files in addition to Herdr terminal IDs.
- Core deps: `litellm` remains optional `[api]` extra; session persistence added to `PhaseRunner`.

## [3.8.0] - 2026-11-26
### Added
- **Responsive TUI:** breakpoints collapse the phase sidebar into a selector on narrow terminals and show a minimum-size notice when the terminal is too small.
- **Theme-aware styling:** the Textual UI uses design tokens (`$primary`, `$surface`, `$panel`, `$accent`, `$success`, `$warning`, `$error`) instead of hardcoded colors, so light and dark themes stay readable.
- **Live progress feedback:** a spinner plus symbolic status (`● Ready`, `✓ Completed`, `! Cancelled`, `✗ Error`) makes long-running phases visibly active.
- **Standalone binary build:** `build.spec`, `scripts/build_binary.sh`, and `scripts/build_binary.ps1` produce a one-file PyInstaller executable.

### Changed
- TUI tests cover wide, narrow, and tiny layouts, phase selection, spinner visibility, cancellation, and error states.

## [3.6.1] - 2026-11-26
### Fixed
- **English auto-detect message:** the smart-defaults notice now reads `ℹ️ Auto-detected spec: ...`, completing the CLI localization.

## [3.6.0] - 2026-11-26
### Added
- **Interactive wizard:** `poseidon run` without arguments or with `-i` asks for phase, spec, and role.
- **Status dashboard:** `poseidon status` renders a Rich table with available phases, every spec's `status:`, and the default role.
- **Smart defaults:** `--spec` is auto-detected when `specs/` contains exactly one `*.spec.md`; `--role` falls back to `default_role` from `config.yaml`, then `tester`.
- **Questionary dependency** for the interactive wizard.

### Changed
- `--phase` on `poseidon run` is optional to enable the wizard.
- Added tests for auto-detection, wizard flow, default role resolution, and status output.

## [3.5.7] - 2026-11-26
### Changed
- **English CLI/TUI:** every user-facing message from the CLI, phase runner, Herdr delegation, prompt framing, and errors is now English.
- **Strict audit traceability:** US-002 was re-audited at version 0.4.0 in round 5 (`audit.5`, 0 blocking findings); its `certified` status and drift report are preserved.

### Added
- Message assertions updated to the English output.

## [3.5.6] - 2026-11-26
### Fixed
- **Drift verdict contract:** the Phase 4 prompt now declares the required `effective_verdict` frontmatter field (`no-drift | drifted | drifted-accepted`), and artifact validation accepts the plain `verdict` fallback defined by skill 05.
- **US-002 certified:** the health endpoint drift report passed with 0 blocking findings and the spec advanced to `certified`.

### Added
- Tests for the drift frontmatter contract and plain-verdict fallback.

## [3.5.5] - 2026-11-26
### Fixed
- **Headless output:** a finished `headless_in_terminal` run with `exit 0` no longer fails when Herdr returns truncated history (`complete=false`); terminal text is display-only and owned artifacts are validated separately.
- **Idempotent transitions:** self-transitions are allowed so Poseidon can write `drift_report` even when an agent already applied the target status.

### Added
- Regression tests for truncated headless reads and an agent-applied `certified` status.

## [3.5.4] - 2026-11-26
### Fixed
- **Lifecycle state gap:** `SpecStatus` now models `implemented`, the state the Keel Nav protocol requires between audit and drift. Adds `audited|approved -> implemented` and `implemented -> observed|certified`.
- **Phase 2 state ownership:** a successful TDD run advances the spec to `implemented` atomically and instructs the agent not to edit `status`, `goldfish_audit`, or `drift_report`. If the agent applied the state itself, Poseidon keeps it and warns instead of failing.

### Added
- Tests for the TDD transition, agent-edited `implemented` status, drift certification from `implemented`, and ODD observation from `implemented`.

## [3.5.3] - 2026-11-24
### Fixed
- **Artifact ownership:** Poseidon calculates and injects exact report paths, reads the actual artifact instead of raw terminal output, validates frontmatter, and uses coherent newer reports as fallback.
- **Atomic state ownership:** the agent cannot advance spec status; Poseidon reconciles audit status and updates `goldfish_audit`/`drift_report` atomically.
- **Resumable waits:** `terminal.wait` timeouts now poll progress and retry until a total deadline, with per-phase overrides and resume instructions.
- **Resume support:** `poseidon run --resume <terminal>` reattaches to live work, and subsequent runs reuse matching live terminals.
- **Prompt cleanup:** Windows prompt-file deletion retries with backoff, warns on remaining locks, and sweeps stale files on startup and atexit.

### Added
- `herdr.total_timeout_seconds` (3600), `progress_interval_seconds` (30), and validated `phase_timeouts`.
- Tests for owned artifacts, verdict metadata, atomic reconciliation, resumable waits, terminal reuse, resume CLI, and cleanup warnings.
- README long-phase/resume guidance, integrity prerequisites, model catalog guidance, and 138-test badge.

- **Debuggability:** `poseidon run --debug` prints exact Herdr commands, JSON-RPC responses, terminal IDs, and `hc attach <id>` instructions while leaving terminals alive for inspection.
- **RPC diagnostics:** `_HerdrSession` logs outgoing requests and matching responses with optional prompt/response content warnings.

### Added
- `herdr.auto_approve` configuration with boolean validation and `auto_approve: true` in `config.yaml`.
- Tests for RPC and terminal debug output, disabled debug mode, `--auto`, model fallback, config validation, and CLI debug propagation.
- README debug guidance, auto-approve risk note, and model precedence documentation.

- **Prompt-file safety:** prompts are written to `.poseidon/tmp/<uuid>.prompt.md` and removed in `finally`, with `.poseidon/tmp/` ignored by Git.
- **Model handling:** `herdr.agent_model` adds `--model "<model>"`; `herdr.agent_args` appends extra arguments. Paths with spaces are quoted.
- **Windows UTF-8:** shared `poseidon.console.configure_utf8_output()` reconfigures legacy cp1252 streams before delegator messages, preventing `UnicodeEncodeError` outside the CLI.
- **Local model propagation:** `LocalCLIDelegator.execute(..., model=...)` forwards models to OpenCode, Claude Code, and Codex without adding `opencode run -` (which is a literal argument).
- **Config validation:** `launch`, `agent_model`, and `agent_args` are validated with allowed values and types; obsolete `fallback_to_subprocess` was removed from `config.yaml`.

### Added
- `herdr.launch: interactive | headless_in_terminal` and documentation for the experimental interactive flow, headless-in-terminal recipe, Windows integrity requirements, and model prerequisites.
- Tests for prompt-file contents and cleanup, command-line quoting, real callers, read failures, UTF-8 output, local model flags, and launch/model/args validation.

- `terminal.wait` fallback when `terminal.send` does not return `wait`; wait results are interpreted by `reason`, `status`, and `exit_code` with explicit `attach`/`read`/`kill` guidance.
- Read validation rejects unstable output (`why`) and incomplete reads while accepting normal full-screen `stitched` history.
- Removed the redundant manual newline from Herdr prompts; Herdr already pastes and submits with Enter.
- OpenCode invocation corrected to `opencode run` (no positional message), matching its actual stdin behavior.
- `machine.exec` headless timeouts are capped at 600 seconds and respect truncation, exit codes, and base64 output.

### Added
- Optional `herdr.mode: headless` for one-shot, non-interactive execution with base64 stdin and stdout decoding.
- Strict `persistent | headless` validation and a 900-second default wait timeout across code, config, and docs.
- Config validation rejects unknown top-level, role, and Herdr keys (including obsolete `fallback_to_subprocess`) and non-string phase-role references.
- New tests for single-session transport, turn reasons, recovery hints, complete/stitched reads, headless execution, and strict configuration.
- README **Troubleshooting Herdr** section with terminal lifecycle, permission handling, and `Ctrl+C` behavior.

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
