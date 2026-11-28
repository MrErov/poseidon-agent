# Contributing to Poseidon Agent

Thanks for taking the time. This repository is also a working demo of Keel Nav, so contributions follow the protocol the tool enforces.

## Ground rules

1. **Never delete a test to make code pass.** The suite is the contract. If a test is wrong, replace it with a better one in the same commit and say so in the PR body.
2. **Red first.** A new behavior starts with a failing test (`213 passing` is the current floor).
3. **Specs before code** for anything larger than a bugfix: write the acceptance criteria first, then implement.
4. **Keep the engine deterministic.** Verdicts come from report frontmatter only, never from stdout, and file writes stay atomic.
5. **`main` is always releasable.** No broken builds, no skipped tests.

## Development setup

```bash
git clone https://github.com/MrErov/poseidon-agent.git
cd poseidon-agent

uv venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv/Scripts/Activate.ps1

uv pip install -e ".[dev]"
```

`[dev]` includes `pytest`, `ruff`, `fastapi` **and `litellm`**. `litellm` is required because the suite patches `poseidon.core.litellm.completion`; an environment installed from a pre-4.1.3 `pyproject.toml` fails 53 of the 213 tests with `AttributeError: None does not have the attribute 'completion'`.

## Run the checks

```bash
uv run pytest          # 213 tests
uv run ruff check .    # lint
```

`pyproject.toml` sets `addopts = "-q"`, so a combined `pytest -q` becomes doubly quiet and prints no summary line. Use `uv run pytest -o addopts="" -q` when you need the count, or rely on the exit code.

## Mapping your work to a Keel Nav phase

| Work you are doing | Phase |
|---|---|
| Recon, reading code, writing conventions docs | `0` / `context` |
| Acceptance criteria, spec file, boundaries | `1a` / `spec` |
| Blind audit of the spec (never sees implementation) | `1b` / `goldfish` |
| Failing tests, then minimum code | `2` / `tdd` |
| End-to-end slice across DB, API, UI | `3` / `odd` |
| Compare built vs. promised, emit verdict | `4` / `drift` |

Phase prompts live in `.meta-skills/` and belong to your project, not to Poseidon.

## Commit messages

Conventional Commits, matching the project history:

```
feat(routing): add ModelRouter for phase-based multi-model orchestration
fix(herdr): run agents headless-in-terminal with real caller
docs(readme): reorganize roadmap and add TOC
chore(release): v4.1.3 integrity release
```

Breaking changes add an `!` after the scope (`feat(cli)!:`) and a `BREAKING CHANGE:` footer.

## Pull requests

1. One topic per PR. Mixed refactors with behavior changes will be asked back.
2. The PR body states the phases applied and the test delta (`213 → 217`).
3. `uv run ruff check .` must be clean. CI runs it on every push and pull request.
4. If the PR touches `release.yml`, describe how you validated the release path.

## Releases

Releases are cut by tagging:

```bash
git tag v4.1.4
git push origin v4.1.4
```

The `Release` workflow builds the Windows installer and the Linux/macOS binaries, then publishes the release. **Never move a tag that has already been published.**

## Platform notes

- Windows: the Python interpreter must run at **Medium Mandatory Level** for the Herdr delegator. A project under `Mandatory Label\Low Mandatory Level` cannot open Herdr's named pipe (`os error 5`). Fix with `icacls ".venv" "/setintegritylevel" "(OI)(CI)M" "/T"`.

## License

By contributing you agree that your work is licensed under the MIT License.