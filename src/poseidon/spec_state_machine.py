"""Specification state machine: frontmatter and transitions."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from poseidon.exceptions import (
    ArtifactSaveError,
    GateError,
    IllegalTransitionError,
    InputValidationError,
)
from poseidon.types import (
    _STATUS_PATTERN,
    SpecStatus,
    _split_frontmatter,
)
from poseidon.types import (
    VALID_TRANSITIONS as _VALID_TRANSITIONS,
)


class SpecStateMachine:
    """Manage spec state: reads, writes, and valid transitions."""

    def __init__(self, console=None):
        self.console = console

    def read_status(self, spec_path: Path) -> SpecStatus:
        """Read the spec's current status from its frontmatter."""
        specification = self._read_file(spec_path, "the spec to read its status")
        frontmatter = self._extract_frontmatter(specification)
        status_str = self._extract_status_from_frontmatter(frontmatter)
        try:
            return SpecStatus(status_str)
        except ValueError:
            return SpecStatus.DRAFT

    def read_frontmatter_fields(self, spec_path: Path) -> dict[str, str]:
        """Read every field in the spec frontmatter."""
        specification = self._read_file(spec_path, "the spec to read frontmatter")
        parts = _split_frontmatter(specification)
        if parts is None:
            return {}
        _, body, _ = parts
        try:
            data = yaml.safe_load(body) or {}
            return {k: str(v) for k, v in data.items()}
        except yaml.YAMLError:
            return {}

    def validate_gate(self, spec_path: str | None, allowed_statuses: set[str]) -> SpecStatus:
        """Validate that the spec has a status allowed by the gate."""
        if not spec_path or not Path(spec_path).is_file():
            raise GateError("Spec not found for gate validation")

        current = self.read_status(Path(spec_path))
        if current.value not in allowed_statuses:
            raise GateError(
                f"GATEKEEPER BLOCKED THE PHASE: the spec has not passed the "
                f"Goldfish audit (current status: {current.value}). Run Phase 1b first."
            )
        return current

    def transition(
        self,
        spec_path: Path,
        target_status: SpecStatus,
        report_path: Path | None = None,
        report_field: str | None = None,
    ) -> None:
        """Perform an atomic state transition."""
        current = self.read_status(spec_path)

        allowed = _VALID_TRANSITIONS.get(current, set())
        if (
            target_status != SpecStatus.AUDITED
            and target_status not in allowed
            and target_status != current
        ):
            allowed_str = ", ".join(s.value for s in allowed)
            raise IllegalTransitionError(
                f"Illegal state transition: {current.value} -> {target_status.value}. "
                f"Valid transitions from {current.value}: {allowed_str}"
            )

        specification = self._read_file(spec_path, "the spec to update")
        if _split_frontmatter(specification) is None:
            raise InputValidationError("The spec does not have valid frontmatter")

        if target_status == SpecStatus.AUDITED:
            updated = self._set_frontmatter_field(
                specification, "status", SpecStatus.AUDITED.value
            )
        else:
            updated = self._set_frontmatter_field(
                specification, "status", target_status.value, only_if=current.value
            )

        if report_field is not None and report_path is not None:
            updated = self._set_frontmatter_field(
                updated, report_field, self._display_path(report_path)
            )

        self._atomic_write(spec_path, updated)

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write atomically: temp file + os.replace."""
        try:
            temp_path = path.with_suffix(path.suffix + ".tmp")
            temp_path.write_text(content, encoding="utf-8")
            os.replace(temp_path, path)
        except OSError as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise ArtifactSaveError(f"Could not write atomically to {path}: {exc}") from exc

    @staticmethod
    def _read_file(path: Path, description: str) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InputValidationError(f"Could not read {description} at {path}: {exc}") from exc

    @staticmethod
    def _extract_frontmatter(content: str) -> str:
        parts = _split_frontmatter(content)
        return parts[1] if parts is not None else ""

    @staticmethod
    def _extract_status_from_frontmatter(frontmatter: str) -> str:
        match = _STATUS_PATTERN.search(frontmatter)
        if match:
            return match.group("value").strip().strip("\"'").lower() or "draft"
        return "draft"

    @classmethod
    def _set_frontmatter_field(
        cls,
        content: str,
        field: str,
        value: str,
        *,
        only_if: str | None = None,
    ) -> str:
        parts = _split_frontmatter(content)
        if parts is None:
            return content

        opening, body, closing = parts
        field_pattern = re.compile(
            rf"^(?P<prefix>[ \t]*{re.escape(field)}[ \t]*:[ \t]*)"
            r"(?P<value>[^\r\n]*?)"
            r"(?P<comment>[ \t]+#[^\r\n]*)?"
            r"(?P<ending>\r?)$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = field_pattern.search(body)

        if match is not None:
            current_value = match.group("value").strip().strip("\"'")
            if only_if is not None and current_value.lower() != only_if.lower():
                return content
            replacement = (
                f"{match.group('prefix')}{value}"
                f"{match.group('comment') or ''}{match.group('ending')}"
            )
            new_body = body[: match.start()] + replacement + body[match.end():]
        elif body.endswith(("\n", "\r")):
            new_body = f"{body}{field}: {value}\n"
        elif body:
            new_body = f"{body}\n{field}: {value}\n"
        else:
            new_body = f"{field}: {value}\n"

        return f"{opening}{new_body}{closing}"

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()