"""Núcleo de ejecución de fases de Poseidón."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import litellm
from rich.console import Console
from rich.markdown import Markdown

_PHASE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_STATUS_PATTERN = re.compile(
    r"^status[ \t]*:[ \t]*(?P<value>[^#\r\n]+?)[ \t]*(?:#.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
_ALLOWED_GATE_STATUSES = {"audited", "approved"}


class PoseidonError(Exception):
    """Error controlado que puede presentarse directamente al usuario."""


class InputValidationError(PoseidonError):
    """Una fase, una ruta o un archivo de entrada no es válido."""


class GateError(PoseidonError):
    """La compuerta de validación impide ejecutar una fase TDD."""


class CompletionError(PoseidonError):
    """LiteLLM no pudo generar una respuesta utilizable."""


class PhaseRunner:
    """Ejecuta fases del proyecto actual sin conservar historial entre llamadas."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def run(self, phase: str, spec_path: str | None, model_name: str) -> str:
        """Valida y ejecuta una fase, devolviendo el Markdown generado."""
        self.validate_gates(phase, spec_path or "")

        phase_file = self._get_phase_file(phase)
        spec_file = Path(spec_path) if spec_path else None

        self._ensure_file(
            phase_file,
            f"No se encontró la Memoria Fría para la fase '{phase}': {phase_file}",
        )
        cold_memory = self._read_file(phase_file, "la Memoria Fría")

        specification: str | None = None
        if spec_file is not None:
            self._ensure_file(
                spec_file,
                f"No se encontró el archivo de especificación: {spec_file}",
            )
            specification = self._read_file(spec_file, "la especificación")

        if "goldfish" in phase.lower() or "1b" in phase.lower():
            self.console.print("Aislando Memoria para Goldfish", style="bold yellow")

        # La Memoria Caliente es siempre una lista local y nueva, sin historial.
        messages = self._build_messages(
            phase=phase,
            spec_path=spec_file,
            cold_memory=cold_memory,
            specification=specification,
        )

        try:
            response = litellm.completion(
                model=model_name,
                messages=messages,
                temperature=0.0,
            )
        except Exception as exc:
            raise CompletionError(
                f"No se pudo ejecutar la fase '{phase}' con el modelo "
                f"'{model_name}': {exc}"
            ) from exc

        content = self._extract_content(response)
        self.console.print(Markdown(content))
        return content

    def validate_gates(self, phase: str, spec_path: str) -> None:
        """Exige una especificación auditada o aprobada antes de una fase TDD."""
        if phase != "2" and "tdd" not in phase.lower():
            return

        if not spec_path or not Path(spec_path).is_file():
            raise GateError(self._gate_message("missing"))

        specification = self._read_file(Path(spec_path), "el spec para el Gatekeeper")
        frontmatter = self._extract_frontmatter(specification)
        status_match = _STATUS_PATTERN.search(frontmatter)
        status = "missing"

        if status_match:
            status = status_match.group("value").strip().strip("\"'").lower() or "missing"

        if status not in _ALLOWED_GATE_STATUSES:
            raise GateError(self._gate_message(status))

    @staticmethod
    def _gate_message(status: str) -> str:
        return (
            "❌ GATEKEEPER BLOQUEÓ LA FASE: El spec no ha pasado la auditoría "
            f"Goldfish (status actual: {status}). Ejecuta la Fase 1b primero."
        )

    @staticmethod
    def _extract_frontmatter(content: str) -> str:
        """Devuelve únicamente el frontmatter inicial, sin el cuerpo Markdown."""
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return ""

        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[1:index])

        return ""

    @staticmethod
    def _get_phase_file(phase: str) -> Path:
        """Resuelve la Memoria Fría desde el proyecto donde se invoca Poseidón."""
        if not _PHASE_PATTERN.fullmatch(phase):
            raise InputValidationError(
                "La fase solo puede contener letras, números, guiones y guiones bajos."
            )
        return Path.cwd() / ".meta-skills" / f"{phase}.md"

    @staticmethod
    def _ensure_file(path: Path, message: str) -> None:
        if not path.is_file():
            raise InputValidationError(message)

    @staticmethod
    def _read_file(path: Path, description: str) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InputValidationError(f"No se pudo leer {description} en {path}: {exc}") from exc

    @staticmethod
    def _build_messages(
        phase: str,
        spec_path: Path | None,
        cold_memory: str,
        specification: str | None,
    ) -> list[dict[str, str]]:
        """Crea una lista nueva; nunca reutiliza ni extiende mensajes anteriores."""
        if spec_path is None:
            user_content = (
                f"Ejecuta la fase '{phase}'.\n\n"
                "No se proporcionó una especificación de entrada para esta fase."
            )
        else:
            user_content = (
                f"Ejecuta la fase '{phase}' sobre la especificación '{spec_path}'.\n\n"
                f"--- INICIO DE LA ESPECIFICACIÓN ---\n"
                f"{specification or ''}\n"
                f"--- FIN DE LA ESPECIFICACIÓN ---"
            )

        return [
            {
                "role": "system",
                "content": cold_memory,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Extrae texto de una respuesta no streaming de LiteLLM."""
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise CompletionError("LiteLLM devolvió una respuesta con formato inesperado.") from exc

        if not isinstance(content, str) or not content.strip():
            raise CompletionError("LiteLLM devolvió una respuesta vacía o sin contenido de texto.")

        return content
