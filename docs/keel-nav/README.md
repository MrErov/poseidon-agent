# ⚓ Keel Nav

> 🛠️ **Looking for a guided runtime?** Try [Poseidon Agent](https://github.com/MrErov/poseidon-agent), which executes this protocol out of the box.

Keel Nav is a **protocol for deterministic, human-in-the-loop software delivery**. It defines the map: phases, templates, gates and conventions. It does not prescribe who or what walks the map — that is the runtime's job.

The Navigator is always in control. Every phase produces inspectable evidence before the next one may begin.

## Two Ways to Sail

| | 🧭 Manual (Navigator + AI assistant) | 🔱 With Poseidón Agent |
|---|---|---|
| **Cold Memory** | You copy `.meta-skills/` prompts into the chat yourself. | Loaded automatically from `.meta-skills/` with alias or exact filename resolution. |
| **Hot Memory** | The chat history accumulates; a later phase can be biased by earlier turns. | A fresh message list per run; Goldfish audits execute in isolation. |
| **Spec Writer (1a)** | You paste the template and hope the output is well-formed. | Generated spec is fence-cleaned and saved atomically to `specs/<name>.spec.md`. |
| **Goldfish Audit (1b)** | You must remember to open a clean session. | Memory isolation is enforced; the verdict is read only from report frontmatter. |
| **Gatekeeper (2)** | You trust yourself not to start TDD on a draft spec. | TDD is blocked at code level unless the spec is `audited` or `approved`. |
| **State transitions** | `status:` is edited by hand; illegal jumps go unnoticed. | `draft → audited → {approved, observed} → certified`; illegal jumps raise `IllegalTransitionError`. |
| **Artifacts** | Files renamed and overwritten ad hoc. | Numbered audits/drift rounds, atomic writes, no silent truncation. |
| **Executors** | Whatever the chat tool offers. | LiteLLM API, local CLIs (Claude Code / Codex / OpenCode) or persistent Herdr terminals. |
| **Audit trail** | Scattered chat logs. | Every verdict, artifact path and transition is persisted in the spec frontmatter. |

> **Same destination, different discipline.** Keel Nav defines the route; Poseidón makes the route executable and verifiable.

## The Phases

| Phase | Alias | Purpose | Artifact |
|-------|-------|---------|----------|
| 0 — Context Bootstrap | `0`, `context` | Map the repository and its bounded contexts | `docs/context/*.md` |
| 1a — Spec Writer | `1a`, `spec` | Produce a bounded, testable specification | `specs/<name>.spec.md` |
| 1b — Goldfish Audit | `1b`, `goldfish` | Blind audit with isolated memory | `specs/<name>.audit.<N>.md` |
| 2 — Strict TDD | `2`, `tdd` | RED → GREEN → REFACTOR per the test plan | console / code |
| 3 — ODD Vertical Slice | `3`, `odd` | Runtime-observable validation | `specs/<name>.observation.md` |
| 4 — Drift Control | `4`, `drift` | Verify code against the spec and certify | `specs/<name>.drift.<N>.md` |

## Spec Contract

The spec frontmatter (line 1) is the single source of truth for state:

```yaml
---
us_id: US-001
status: draft            # draft | audited | approved | observed | certified
goldfish_audit: pending
drift_report: pending
---
```

Only these transitions are valid:

```text
draft ──(1b audited)──> audited ──(Navigator)──> approved
                                   └──(3)──> observed
approved / observed ──(4 no-drift)──> certified
```

A report's verdict must live in **its own frontmatter**:

```yaml
---
effective_verdict: audited
---
```

Prose mentions like `verdict: audited` in the body are never authoritative.

## Templates

- [`templates/spec.template.md`](https://github.com/MrErov/poseidon-agent/blob/main/templates/spec.template.md)
- [`templates/drift-report.template.md`](https://github.com/MrErov/poseidon-agent/blob/main/templates/drift-report.template.md)
- [`templates/test-plan.template.md`](https://github.com/MrErov/poseidon-agent/blob/main/templates/test-plan.template.md)

## Why a Protocol at All?

An LLM without a map optimizes for plausibility. A protocol optimizes for **evidence**: bounded specs, isolated audits, deterministic gates and a Navigator who signs off each transition. Keel Nav supplies the map; [Poseidón Agent](https://github.com/MrErov/poseidon-agent) walks it.
