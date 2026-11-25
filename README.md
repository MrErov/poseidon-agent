<div align="center">
  <img src="docs/assets/logo.png" alt="Poseidon Agent Logo" width="180">
  <h1>🔱 Poseidon Agent</h1>
  <p><strong>The guided autonomous runtime for Keel Nav.</strong> A local-first AI agent with 3-layer cognitive memory.</p>
  <p>
    <a href="https://github.com/MrErov/poseidon-agent/releases/latest">
      <img alt="Version" src="https://img.shields.io/badge/version-v3.5.1-blue.svg" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/actions/workflows/ci.yml">
      <img alt="Build Status" src="https://img.shields.io/github/actions/workflow/status/MrErov/poseidon-agent/ci.yml?branch=main" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/blob/main/LICENSE">
      <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/tree/main/tests">
      <img alt="Tests" src="https://img.shields.io/badge/tests-115%20passing-brightgreen.svg" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/releases/latest">
      <img alt="Release" src="https://img.shields.io/github/v/release/MrErov/poseidon-agent?include_prereleases&sort=semver" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/issues">
      <img alt="Issues" src="https://img.shields.io/github/issues/MrErov/poseidon-agent" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/stargazers">
      <img alt="Stars" src="https://img.shields.io/github/stars/MrErov/poseidon-agent?style=social" />
    </a>
  </p>
</div>

<div align="center">
  <img src="docs/assets/tui-demo.gif" alt="Poseidon Agent TUI demo" width="800">
</div>

Poseidón is the deterministic execution engine for the **Keel Nav** protocol. It turns a guided map into auditable software: it isolates memory, delegates inference, persists artifacts and enforces state transitions — the Navigator stays in control of every step.

---

## 🎯 Why Poseidon?

| | Free-Loop Agents (Hermes, AutoGPT, etc.) | **Poseidon Agent** |
|:---|:---|:---|
| **Memory** | Unbounded conversation history; context drifts between turns | **3-Layer Cognitive Memory**: Immutable Cold Memory on disk, fresh Hot Memory per run, Context/Graph Memory injected only where needed |
| **Validation** | Self-reports success; no deterministic gate | **Gatekeeper + Strict State Machine**: TDD blocked until spec is `audited`/`approved`; verdicts parsed only from report frontmatter |
| **Orchestration** | Model improvises next action | **The Map Rules**: Thin orchestrator coordinates `SpecStateMachine`, `PromptBuilder`, `ExecutionEngine` |
| **Auditability** | Opaque decision trail | **Full Traceability**: Every phase produces immutable artifacts; every transition logged and verifiable |
| **Control** | Agent decides next step | **Human-in-the-Loop**: Gatekeeper blocks unapproved work; Navigator authorizes every phase transition |

> **Poseidon doesn't replace the Navigator—it makes the Navigator's intent executable and verifiable.**

> **Poseidon doesn't replace the Navigator—it makes the Navigator's intent executable and verifiable.**

---

## 🏛️ Four Pillars of Poseidon

| Pillar | Description |
|--------|-------------|
| **🎯 Guided 5-Phase Engine** (Keel Nav Native) | Context Bootstrap → Spec Writer → Goldfish Audit → Strict TDD → ODD Vertical Slice → Drift Control. Every phase gated by deterministic transitions. |
| **🏠 Full Local & OS Agency** | Persistent Herdr terminals, local CLIs, isolated subprocesses — no shell, prompts via stdin. Your machine, your rules. |
| **🛡️ Human-in-the-Loop** | Gatekeeper blocks unapproved work; artifacts and verdicts keep every decision inspectable. The human stays in command. |
| **🌐 Multi-Channel** | CLI today, interactive Textual TUI now, future desktop channels. One engine, multiple interfaces. |

## Architecture

```mermaid
graph LR
    UI["CLI / TUI"] --> Runner["PhaseRunner<br/>(thin orchestrator)"]
    Runner --> SM["SpecStateMachine<br/>frontmatter · gates · atomic writes"]
    Runner --> PB["PromptBuilder<br/>cold memory · context · Graphify"]
    Runner --> EE["ExecutionEngine"]
    EE --> API["LiteLLM / NVIDIA NIM"]
    EE --> CLI["Claude Code · Codex · OpenCode"]
    EE --> HERDR["Herdr (JSON-RPC 2.0)"]
    API --> ART["Artifacts + Spec status"]
    CLI --> ART
    HERDR --> ART
    ART --> SM
```

## Ecosystem

| Component | Responsibility |
|-----------|----------------|
| **Keel Nav** | Defines the phases, templates, gates and conventions that make up Cold Memory. |
| **Poseidón Agent** | Resolves phases, isolates memory, delegates inference, saves artifacts and enforces the state machine. |
| **DeepSeek plugin** | Provides invocation inside the DeepSeek experience; it neither replaces the engine nor implies use of the DeepSeek API. |
| **NVIDIA NIM or local CLIs** | Execute inference through LiteLLM or Claude Code, Codex and OpenCode. |
| **Graphify MCP** | Optionally injects dynamic code-graph context into Phases 1a and 1b. |

## Memory Model

- **Cold Memory:** instructions resolved from `.meta-skills/` using a phase alias or exact filename; phases belong to the target project, not to Poseidón.
- **Hot Memory:** a new message list for every call, with no previous history.
- **Context:** the content of `--context` is injected before `--spec` into Hot Memory.
- **Goldfish Audit:** any phase resolved as `02-egm-goldfish-audit` displays its memory-isolation warning and runs without history.

## Phase Aliases

| Alias | File in `.meta-skills/` |
|-------|--------------------------|
| `0`, `00`, `context` | `00-context-bootstrap.md` |
| `1a`, `spec` | `01-sdd-spec-writer.md` |
| `1b`, `goldfish` | `02-egm-goldfish-audit.md` |
| `2`, `tdd` | `03-tdd-cycle.md` |
| `3`, `odd` | `04-odd-vertical-slice.md` |
| `4`, `drift` | `05-drift-control.md` |

You can also provide the exact filename, with or without `.md`. If the phase does not match an alias, Poseidón searches for a Markdown file whose name starts with or contains the phase. If no match is found, it stops with a controlled error.

## Requirements and Installation

Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv/Scripts/Activate.ps1
uv pip install -e .
```

Create a `.env` file with your NVIDIA NIM credential (Graphify is optional):

```dotenv
NVIDIA_NIM_API_KEY=...
# GRAPHIFY_MCP_URL=https://api.graphify.com/mcp
```

## Usage

Run Poseidón from the project root containing `.meta-skills/`:

```bash
poseidon run --phase 00-context-bootstrap --model nvidia_nim/<available-model>
poseidon run --phase 1a --spec specs/US-001.md --context docs/context/api.md --model nvidia_nim/<available-model>
poseidon run --phase 1b --spec specs/US-001.md --context docs/context/api.md --model nvidia_nim/<available-model>
```

### Local Executors

With `--executor api` (default) `--model` is required. Otherwise the CLI manages its own auth:

```bash
poseidon run --phase 1b --spec specs/US-001.md --executor claude-code
poseidon run --phase 2 --spec specs/US-001.md --executor codex
poseidon run --phase 0 --executor opencode
```

| Executor | Invocation |
|----------|------------|
| `claude-code` | `claude -p --output-format text` (prompt via stdin) |
| `codex` | `codex exec -` (prompt via stdin) |
| `opencode` | `opencode run` (no positional message; prompt via stdin) |

All subprocesses use `shell=False`, a 300 s timeout and controlled errors. Override binaries with `POSEIDON_CLAUDE_CODE_BIN`, `POSEIDON_CODEX_BIN` or `POSEIDON_OPENCODE_BIN`.

### Agent Roles & Herdr

```yaml
version: 2
roles:
  architect: { executor: api, model: nvidia_nim/moonshotai/kimi-k2-instruct }
  tester:    { executor: opencode, model: null, runtime: herdr, name_prefix: poseidon-tester }
phase_roles:
  0: architect
  1a: architect
  1b: tester
  2: tester
  3: tester
  4: architect
herdr:
  executable: hc
  wait_timeout_seconds: 900
  read_lines: 1000
  keep: true
  outlive_parent: true
  mode: persistent  # persistent | headless
  launch: headless_in_terminal  # interactive | headless_in_terminal
  agent_model: ""  # optional; adds --model "<model>" when set
  agent_args: []   # extra CLI arguments appended to the agent command
```

Precedence: CLI flags → role → `phase_roles` → API defaults. Herdr uses one JSON-RPC 2.0 session per run over `hc connect`, with a stable caller identity and strict response validation.

**Headless-in-terminal (default):** Poseidon writes the prompt to `.poseidon/tmp/<uuid>.prompt.md`, starts a non-interactive command with `terminal.run`, waits for the command to exit with `terminal.wait`, and retrieves the response with `terminal.read`. Prompt files are always deleted in `finally`; `.poseidon/tmp/` is gitignored. Shell redirection keeps prompt contents out of Windows' 8191-character command-line limit. Set `herdr.agent_model` to add `--model "<model>"`; `agent_args` appends extra arguments. Paths with spaces are quoted.

**Interactive (experimental):** the existing TUI flow uses `terminal.send(wait: true)` with the **real terminal address as caller**, falling back to `terminal.wait` with the same address. This requires an agent that reports status to Herdr. OpenCode's TUI may report no status and no turn, so an interactive agent that answers and remains open cannot be waited on reliably. Use `launch: headless_in_terminal` for deterministic completion.

**Headless machine execution:** `herdr.mode: headless` still supports one-shot `machine.exec` calls with base64 stdin, capped at 600 seconds. OpenCode uses `opencode run --format json` with stdin (no `-` argument).


### Troubleshooting Herdr

#### Environment prerequisites (B1)

On Windows, the Python interpreter running Poseidon must have **Medium Mandatory Level** integrity. If you see `os error 5` when calling `hc connect`, check `icacls <project-path>` and `whoami /groups`: a project marked `Mandatory Label\\Low Mandatory Level` runs Python in Low IL and cannot open Herdr's Medium-IL named pipe. Use Python outside the Low-IL directory or, as an administrator, run `icacls "C:\path\to\project" /setintegritylevel (OI)(CI)M /T`.

The OpenCode model must exist in the catalog shown by `opencode models`. If it is missing, pass `herdr.agent_model` explicitly. An empty `agent_model` leaves model selection to OpenCode's default configuration, so an invalid default model can still fail.

#### Verified headless-in-terminal recipe

```text
terminal.run  line='opencode run --model "<model>" < "<prompt_file>"'
terminal.wait timeout=300  → {"ended":true,"exit_code":0,"reason":"exit"}
terminal.read lines=300    → how=history complete=True → agent output
```

Herdr delivers pasted input after roughly 3 seconds of terminal quiet (or up to 60 seconds while a draft is active). A running interactive interface is not evidence of failure; Herdr distinguishes the **agent turn** from the **process lifetime**.

- `hc ls --all` — lists live and finished terminals, including exit codes.
- `hc attach tN` — attaches to a live terminal to inspect prompts or permission dialogs.
- `hc read tN` — reads current output without attaching.
- `hc get tN` — shows terminal state and last reported status.
- `hc kill tN` — stops a terminal while preserving its record for inspection.
- `hc rm tN` — removes a terminal record after you no longer need it.

When OpenCode pauses for file-read or command permissions, attach with `hc attach tN`, review the exact action, and respond in that terminal. Poseidon does not auto-approve those requests.

**Ctrl+C does not kill a Herdr terminal.** It only closes the client. The agent remains alive in `herdr-core` and can be recovered with `hc attach`. A timeout is a check-in, not proof that the agent stopped working; inspect `reason` and `status` before assuming failure.

Persistent-mode timeout errors include the terminal address and `attach`/`read`/`kill` hints. `reason: message` means another terminal sent your agent a message; `reason: not_started` means no agent turn began. A completed `read` with `how: stitched` is normal for a full-screen TUI.

### Textual TUI

```bash
poseidon tui
```

Select a phase, fill **Spec Path** / **Context Path**, press **Ctrl+R** to run in a background worker, **Ctrl+X** to cancel, **Ctrl+Q** to quit. Output is forwarded to the `RichLog` without blocking the interface.

### Automatic Artifacts

| Phase | Generated file |
|-------|----------------|
| `1a` | `specs/<name>.spec.md` |
| `1b` | `specs/<name>.audit.<N>.md` |
| `2` | Console only |
| `3` | `specs/<name>.observation.md` |
| `4` | `specs/<name>.drift.<N>.md` |

Writes are atomic (temp file + `os.replace`). Verdicts come only from the report frontmatter via `yaml.safe_load`; free text is ignored.

### Spec State Machine

Valid transitions: `draft → audited → {approved, observed} → certified`. Illegal jumps raise `IllegalTransitionError`. Phase 2 requires `audited` or `approved` before any inference call.

## Development

```bash
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check .
vhs demo.tape   # regenerates docs/assets/tui-demo.gif
```

## Changelog Highlights

- **v3.5.1** — Headless-in-terminal delegation: prompt files, real interactive caller, explicit model handling, and Windows UTF-8 safety.
- **v3.5.0** — Herdr turn semantics: persistent JSON-RPC sessions, turn-aware waits, headless machine execution, and strict mode/config validation.
- **v3.4.0** — Marketing Release: product-style READMEs, VHS demo script and Keel Nav protocol README.
- **v3.3.0** — Production-Ready Architecture: decoupled `PhaseRunner`, atomic persistence and strict config validation.
- **v3.2.0** — TUI inputs, Herdr JSON-RPC hardening, 300 s timeout, `Ctrl+X` cancellation.
- **v3.1.0** — Secure Gatekeeper, strict state transitions, frontmatter-only verdict extraction.

## License

MIT License.
