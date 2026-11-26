"""Tipos y constantes compartidas de Poseidón."""

from __future__ import annotations

import re
from enum import Enum


class SpecStatus(str, Enum):
    """Estados válidos del ciclo de vida de una especificación."""

    DRAFT = "draft"
    AUDITED = "audited"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    OBSERVED = "observed"
    CERTIFIED = "certified"


# Transiciones permitidas: estado_origen -> {estados_destino_permitidos}
VALID_TRANSITIONS: dict[SpecStatus, set[SpecStatus]] = {
    SpecStatus.DRAFT: {SpecStatus.AUDITED},
    SpecStatus.AUDITED: {
        SpecStatus.APPROVED,
        SpecStatus.IMPLEMENTED,
        SpecStatus.OBSERVED,
    },
    SpecStatus.APPROVED: {
        SpecStatus.IMPLEMENTED,
        SpecStatus.OBSERVED,
        SpecStatus.CERTIFIED,
    },
    SpecStatus.IMPLEMENTED: {SpecStatus.OBSERVED, SpecStatus.CERTIFIED},
    SpecStatus.OBSERVED: {SpecStatus.CERTIFIED},
    SpecStatus.CERTIFIED: set(),
}

# Alias for backward compatibility
_VALID_TRANSITIONS = VALID_TRANSITIONS


_PHASE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_STATUS_PATTERN = re.compile(
    r"^status[ \t]*:[ \t]*(?P<value>[^#\r\n]+?)[ \t]*(?:#.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
_ALLOWED_GATE_STATUSES = {SpecStatus.AUDITED.value, SpecStatus.APPROVED.value}
_LOCAL_EXECUTORS = {"claude-code", "codex", "opencode"}
_PHASE_ALIASES: dict[str, str] = {
    "0": "00-context-bootstrap.md",
    "00": "00-context-bootstrap.md",
    "context": "00-context-bootstrap.md",
    "1a": "01-sdd-spec-writer.md",
    "spec": "01-sdd-spec-writer.md",
    "1b": "02-egm-goldfish-audit.md",
    "goldfish": "02-egm-goldfish-audit.md",
    "2": "03-tdd-cycle.md",
    "tdd": "03-tdd-cycle.md",
    "3": "04-odd-vertical-slice.md",
    "odd": "04-odd-vertical-slice.md",
    "4": "05-drift-control.md",
    "drift": "05-drift-control.md",
}
_PHASE_KINDS_BY_PREFIX = {
    "00": "context",
    "01": "spec",
    "02": "goldfish",
    "03": "tdd",
    "04": "odd",
    "05": "drift",
}


# Deprecated patterns - kept for test compatibility
_VERDICT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key>effective_verdict|verdict)[ \t]*:[ \t]*"
    r"['\"]?(?P<verdict>audited|rejected)\b",
    re.IGNORECASE,
)
_DRIFT_VERDICT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key>effective_verdict|verdict)[ \t]*:[ \t]*"
    r"['\"]?(?P<verdict>no-drift|drifted-accepted|drifted)\b",
    re.IGNORECASE,
)
_OBSERVATION_VERDICT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key>effective_verdict|verdict|status)[ \t]*:[ \t]*"
    r"['\"]?(?P<verdict>approved|observed)\b",
    re.IGNORECASE,
)


def _split_frontmatter(content: str) -> tuple[str, str, str] | None:
    """Separa el delimitador inicial, el cuerpo YAML y el resto del documento."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            opening = lines[0]
            body = "".join(lines[1:index])
            closing = "".join(lines[index:])
            return opening, body, closing
    return None