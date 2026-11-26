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
