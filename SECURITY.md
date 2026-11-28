# Security Policy

Poseidon Agent is an **execution engine**: it runs prompts through third-party models and through local coding CLIs, writes files on your machine and spawns terminals. Treat every agent it launches as an untrusted process.

## Supported versions

| Version | Supported |
|---------|-----------|
| 4.1.x   | Yes       |
| < 4.1   | No        |

Only the latest tagged release receives security fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

1. Go to <https://github.com/MrErov/poseidon-agent/security/advisories/new>
2. Include the affected version, Python version, OS, executor (`api`, `claude-code`, `codex`, `opencode`, `herdr`) and a minimal reproduction.

Do **not** open a public issue for a security problem. Expect an acknowledgement within 72 hours.

## What belongs in scope

Anything in `src/poseidon`, `scripts/build_binary.ps1`, `scripts/build_binary.sh` or `.github/workflows/`:

- **Path traversal** — a phase alias, spec path or context path that escapes the project root and reads or writes outside the working directory.
- **Credential exposure** — `NVIDIA_NIM_API_KEY` or MCP tokens appearing in logs, session files under `.poseidon/sessions/`, or error traces.
- **Herdr delegation** — unsafe JSON-RPC argument construction over `hc connect`, or unvalidated `terminal.read` output being trusted as a report verdict.
- **Local executors** — shell injection through `POSEIDON_CLAUDE_CODE_BIN`, `POSEIDON_CODEX_BIN`, `POSEIDON_OPENCODE_BIN`, spec filenames or context paths.
- **Frontmatter parsing** — a spec report whose frontmatter can make the operator read a verdict that the executed phase never actually verified.
- **Writes outside `.poseidon/tmp/`** — a phase or `mcp list` that writes outside its declared working directory.
- **Binary build** — PyInstaller or Inno Setup packaging that bundles code the build does not need.

## What is out of scope

- What a third-party CLI (Claude Code, Codex, OpenCode, LiteLLM account, Herdr's own server) decides to do with your files.
- Misconfigured API keys or an exposed `.env` file on a machine already trusted.

## Hardening recommendations

- Keep `auto_approve: false` for OpenCode unless the task is disposable.
- Never point `executor: herdr` at a terminal that already holds sensitive secrets.
- Keep `.poseidon/tmp/` gitignored (it is by default): prompt files are deleted in `finally`, but a crash could leave one behind.
- Never commit `.env`. Templates are in `.env.example`.
- Run `poseidon doctor` after model changes: it validates binaries, `.meta-skills/` and keys.

## A note on prompt injection

Poseidon isolates memory per run for exactly this reason: Phase 1b, the blind audit, never sees the implementation, and `02-egm-goldfish-audit.md` states its memory-isolation warning.

Memory isolation is not a sandbox. A malicious prompt read as context can still ask a local CLI to write files. Always run phases over code you have already committed somewhere.