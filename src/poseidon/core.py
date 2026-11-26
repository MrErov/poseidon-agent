"""Poseidón phase execution core (orchestrator)."""

from __future__ import annotations

import re
from pathlib import Path

import litellm  # noqa: F401 - re-exported for backward compatibility with tests
from rich.console import Console
from rich.markdown import Markdown

from poseidon.delegator import LocalCLIDelegator
from poseidon.exceptions import (
    ArtifactSaveError,
    CompletionError,  # noqa: F401 - re-exported for backward compatibility
    GateError,  # noqa: F401 - re-exported for backward compatibility
    IllegalTransitionError,
    InputValidationError,
    PoseidonError,  # noqa: F401 - re-exported for backward compatibility
)
from poseidon.execution_engine import ExecutionEngine
from poseidon.herdr_delegator import HerdrDelegator
from poseidon.prompt_builder import PromptBuilder
from poseidon.spec_state_machine import SpecStateMachine
from poseidon.types import (
    _ALLOWED_GATE_STATUSES,
    _LOCAL_EXECUTORS,
    _PHASE_ALIASES,
    _PHASE_KINDS_BY_PREFIX,
    _PHASE_PATTERN,
    SpecStatus,
    _split_frontmatter,
)


class PhaseRunner:
    """Orchestrate phase execution across StateMachine, PromptBuilder, and ExecutionEngine."""

    def __init__(
        self,
        console: Console | None = None,
        delegator: LocalCLIDelegator | None = None,
        herdr_delegator: HerdrDelegator | None = None,
    ) -> None:
        self.console = console or Console()
        self.state_machine = SpecStateMachine(console=self.console)
        self.prompt_builder = PromptBuilder(console=self.console)
        self.execution_engine = ExecutionEngine(
            console=self.console, delegator=delegator, herdr_delegator=herdr_delegator
        )
        # Backward compatibility: expose delegator directly
        self.delegator = self.execution_engine.delegator

    def run(
        self,
        phase: str,
        spec_path: str | None,
        model_name: str | None = None,
        context_path: str | None = None,
        executor: str = "api",
        herdr_agent: str | None = None,
    ) -> str:
        """Validate and run a phase, saving its artifact when applicable."""
        executor = executor.strip().lower()
        if executor != "api" and executor not in _LOCAL_EXECUTORS | {"herdr"}:
            raise InputValidationError(f"Unsupported executor: '{executor}'.")
        if executor == "api" and not (model_name and model_name.strip()):
            raise InputValidationError(
                "The --model parameter is required when executor='api'."
            )

        phase_file = self._resolve_phase_file(phase)
        phase_kind = self._phase_kind(phase, phase_file)
        spec_file = Path(spec_path) if spec_path else None
        context_file = Path(context_path) if context_path else None

        # Validate gates using the resolved phase_kind
        if phase_kind == "tdd":
            self.state_machine.validate_gate(spec_path, _ALLOWED_GATE_STATUSES)

        self._ensure_file(
            phase_file,
            f"Cold memory not found for phase '{phase}': {phase_file}",
        )
        cold_memory = self._read_file(phase_file, "cold memory")

        specification: str | None = None
        if spec_file is not None:
            self._ensure_file(
                spec_file, f"Specification file not found: {spec_file}"
            )
            specification = self._read_file(spec_file, "the specification")

        context: str | None = None
        if context_file is not None:
            self._ensure_file(
                context_file, f"Context file not found: {context_file}"
            )
            context = self._read_file(context_file, "the context")

        graph_context = self.prompt_builder.fetch_graph_context_if_needed(
            phase_kind, spec_file, context_file
        )

        if phase_kind == "goldfish":
            self.console.print("Isolating memory for Goldfish", style="bold yellow")

        artifact_path = (
            self._artifact_path(phase_kind, spec_file, context_file)
            if executor == "herdr"
            else None
        )
        messages = self.prompt_builder.build_messages(
            phase=phase,
            spec_path=spec_file,
            cold_memory=cold_memory,
            specification=specification,
            context=context,
            graph_context=graph_context,
            artifact_path=artifact_path,
            preserve_spec_state=phase_kind == "tdd",
            phase_kind=phase_kind,
        )

        content = self.execution_engine.execute(
            messages,
            executor,
            model_name,
            herdr_agent,
            phase_kind=phase_kind,
            artifact_path=artifact_path,
        )

        self.console.print(Markdown(content))

        if executor == "herdr" and artifact_path is not None:
            owned_path = self.execution_engine.herdr_delegator.last_artifact_path
            if owned_path is None:
                raise ArtifactSaveError(
                    "Herdr did not produce a readable artifact for this phase."
                )
            artifact_path = owned_path
            self.console.print(
                f"✅ Saved to {self._display_path(artifact_path)}",
                style="green",
                markup=False,
            )
        else:
            artifact_path = self._save_artifact(phase_kind, content, spec_file, context_file)
        if phase_kind in {"goldfish", "odd", "drift", "tdd"}:
            self._update_spec_metadata(spec_file, content, artifact_path, phase_kind)

        return content

    def _save_artifact(
        self,
        phase_kind: str,
        content: str,
        spec_path: Path | None,
        context_path: Path | None,
    ) -> Path | None:
        artifact_path = self._artifact_path(phase_kind, spec_path, context_path)
        if artifact_path is None:
            return None

        clean_content = self._strip_markdown_fences(content)

        try:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_machine._atomic_write(artifact_path, clean_content)
        except OSError as exc:
            raise ArtifactSaveError(
                f"Could not save the artifact to {artifact_path}: {exc}"
            ) from exc

        self.console.print(
            f"✅ Saved to {self._display_path(artifact_path)}",
            style="green",
            markup=False,
        )
        return artifact_path

    def _update_spec_metadata(
        self,
        spec_path: Path | None,
        report_content: str,
        report_path: Path | None,
        phase_kind: str = "goldfish",
    ) -> None:
        if spec_path is None:
            return

        if phase_kind == "goldfish":
            verdict = self._extract_strict_verdict(report_content, "goldfish")
            if verdict != "audited":
                self.console.print(
                    "⚠️ Audit rejected. The spec remains in draft.",
                    style="yellow",
                    markup=False,
                )
                return
            target_status = SpecStatus.AUDITED
            report_field = "goldfish_audit"
            success_message = "✅ Spec updated to status: audited"
        elif phase_kind == "tdd":
            target_status = SpecStatus.IMPLEMENTED
            report_field = None
            success_message = "✅ Spec updated to status: implemented"
            if self.state_machine.read_status(spec_path) == target_status:
                self.console.print(
                    "⚠️ The spec was already in status: implemented; "
                    "Poseidon did not rewrite it.",
                    style="yellow",
                    markup=False,
                )
                return
        elif phase_kind == "odd":
            verdict = self._extract_strict_verdict(report_content, "odd")
            if verdict not in {"approved", "observed"}:
                self.console.print(
                    "✅ ODD observation saved", style="green", markup=False
                )
                return
            target_status = SpecStatus.OBSERVED
            report_field = None
            success_message = "✅ Spec updated to status: observed"
        elif phase_kind == "drift":
            verdict = self._extract_strict_verdict(report_content, "drift")
            if verdict == "drifted":
                self.console.print(
                    "❌ Drift rejected. The spec cannot be certified",
                    style="red",
                    markup=False,
                )
                return
            if verdict not in {"no-drift", "drifted-accepted"}:
                self.console.print(
                    "⚠️ No certifiable Drift verdict was found; the spec was not changed.",
                    style="yellow",
                    markup=False,
                )
                return
            target_status = SpecStatus.CERTIFIED
            report_field = "drift_report"
            success_message = "✅ Drift certified. Spec updated to status: certified"
        else:
            raise InputValidationError(
                f"Unsupported phase kind for metadata update: {phase_kind}"
            )

        try:
            self.state_machine.transition(
                spec_path, target_status, report_path, report_field
            )
        except IllegalTransitionError:
            raise
        except ArtifactSaveError:
            raise
        except Exception as exc:
            raise ArtifactSaveError(f"Could not update the spec: {exc}") from exc

        self.console.print(success_message, style="green", markup=False)

    @staticmethod
    def _strip_markdown_fences(content: str) -> str:
        stripped = content.strip()
        fence_pattern = re.compile(
            r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE
        )
        match = fence_pattern.match(stripped)
        if match:
            return match.group(1)
        return content

    @staticmethod
    def _extract_strict_verdict(report_content: str, phase_kind: str) -> str | None:
        import yaml

        parts = _split_frontmatter(report_content)
        if parts is None:
            return None
        _, frontmatter_body, _ = parts
        try:
            data = yaml.safe_load(frontmatter_body) or {}
        except yaml.YAMLError:
            return None
        for key in ("effective_verdict", "verdict", "status"):
            if key in data:
                value = str(data[key]).strip().lower()
                if value:
                    return value
        return None

    @staticmethod
    def _is_goldfish_phase(phase: str) -> bool:
        normalized_phase = phase.lower()
        return "1b" in normalized_phase or "goldfish" in normalized_phase

    @classmethod
    def _phase_kind(cls, phase: str, phase_file: Path) -> str:
        kind = _PHASE_KINDS_BY_PREFIX.get(phase_file.stem[:2])
        if kind is not None:
            return kind
        normalized_phase = phase.lower()
        if cls._is_goldfish_phase(phase):
            return "goldfish"
        if normalized_phase == "2" or "tdd" in normalized_phase:
            return "tdd"
        if normalized_phase in {"1a", "spec"}:
            return "spec"
        if normalized_phase in {"0", "00", "context"}:
            return "context"
        if normalized_phase in {"3", "odd"}:
            return "odd"
        if normalized_phase in {"4", "drift"}:
            return "drift"
        return "unknown"

    def _artifact_path(
        self,
        phase_kind: str,
        spec_path: Path | None,
        context_path: Path | None,
    ) -> Path | None:
        if phase_kind not in {"spec", "goldfish", "odd", "drift"}:
            return None

        spec_name = self._spec_name(spec_path, context_path)
        if spec_name is None:
            self.console.print(
                "⚠️ Could not determine the spec name; the artifact was not saved.",
                style="yellow",
            )
            return None

        specs_dir = Path.cwd() / "specs"
        if phase_kind == "spec":
            return specs_dir / f"{spec_name}.spec.md"
        if phase_kind == "goldfish":
            audit_number = self._next_audit_number(specs_dir, spec_name)
            return specs_dir / f"{spec_name}.audit.{audit_number}.md"
        if phase_kind == "odd":
            return specs_dir / f"{spec_name}.observation.md"
        drift_number = self._next_drift_number(specs_dir, spec_name)
        return specs_dir / f"{spec_name}.drift.{drift_number}.md"

    @staticmethod
    def _spec_name(spec_path: Path | None, context_path: Path | None) -> str | None:
        for candidate in (spec_path, context_path):
            if candidate is None:
                continue
            name = candidate.name
            lowered = name.lower()
            for suffix in (".spec.md", ".md"):
                if lowered.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            if name:
                return name
        return None

    @staticmethod
    def _next_audit_number(specs_dir: Path, spec_name: str) -> int:
        return PhaseRunner._next_artifact_number(specs_dir, spec_name, "audit")

    @staticmethod
    def _next_drift_number(specs_dir: Path, spec_name: str) -> int:
        return PhaseRunner._next_artifact_number(specs_dir, spec_name, "drift")

    @staticmethod
    def _next_artifact_number(
        specs_dir: Path, spec_name: str, artifact_kind: str
    ) -> int:
        if not specs_dir.is_dir():
            return 1
        artifact_pattern = re.compile(
            rf"^{re.escape(spec_name)}\.{re.escape(artifact_kind)}\.(\d+)\.md$",
            re.IGNORECASE,
        )
        try:
            entries = list(specs_dir.iterdir())
        except OSError as exc:
            raise ArtifactSaveError(
                f"Could not inspect the specs directory {specs_dir}: {exc}"
            ) from exc
        numbers = [
            int(match.group(1))
            for path in entries
            if path.is_file() and (match := artifact_pattern.match(path.name))
        ]
        return max(numbers, default=0) + 1

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _resolve_phase_file(phase: str) -> Path:
        normalized = phase.strip()
        if normalized.lower().endswith(".md"):
            normalized = normalized[:-3]
        if not normalized or not _PHASE_PATTERN.fullmatch(normalized):
            raise InputValidationError(
                "A phase may contain only letters, numbers, hyphens, and underscores."
            )
        skills_dir = Path.cwd() / ".meta-skills"
        normalized_lower = normalized.lower()
        alias = _PHASE_ALIASES.get(normalized_lower)
        if alias is not None:
            return skills_dir / alias
        exact_file = skills_dir / f"{normalized}.md"
        if exact_file.is_file():
            return exact_file
        if skills_dir.is_dir():
            try:
                candidates = sorted(
                    (
                        path
                        for path in skills_dir.iterdir()
                        if path.is_file() and path.suffix.lower() == ".md"
                    ),
                    key=lambda path: path.name.lower(),
                )
            except OSError as exc:
                raise InputValidationError(
                    f"Could not read the phases directory {skills_dir}: {exc}"
                ) from exc
            starts_with = [
                path
                for path in candidates
                if path.stem.lower().startswith(normalized_lower)
            ]
            if starts_with:
                return starts_with[0]
            contains = [
                path for path in candidates if normalized_lower in path.stem.lower()
            ]
            if contains:
                return contains[0]
        raise InputValidationError(
            f"Cold memory not found for phase '{phase}' in {skills_dir}"
        )

    @staticmethod
    def _ensure_file(path: Path, message: str) -> None:
        if not path.is_file():
            raise InputValidationError(message)

    @staticmethod
    def _read_file(path: Path, description: str) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InputValidationError(f"Could not read {description} at {path}: {exc}") from exc