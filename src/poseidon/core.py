"""Núcleo de ejecución de fases de Poseidón."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import litellm
from rich.console import Console
from rich.markdown import Markdown

from poseidon.mcp_client import fetch_graph_context

_PHASE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_STATUS_PATTERN = re.compile(
    r"^status[ \t]*:[ \t]*(?P<value>[^#\r\n]+?)[ \t]*(?:#.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
_ALLOWED_GATE_STATUSES = {"audited", "approved"}
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
_VERDICT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key>effective_verdict|verdict)[ \t]*:[ \t]*"
    r"['\"]?(?P<verdict>audited|rejected)\b",
    re.IGNORECASE,
)


class PoseidonError(Exception):
    """Error controlado que puede presentarse directamente al usuario."""


class InputValidationError(PoseidonError):
    """Una fase, una ruta o un archivo de entrada no es válido."""


class GateError(PoseidonError):
    """La compuerta de validación impide ejecutar una fase TDD."""


class CompletionError(PoseidonError):
    """LiteLLM no pudo generar una respuesta utilizable."""


class ArtifactSaveError(PoseidonError):
    """No se pudo guardar un artefacto o un metadato generado por una fase."""


class PhaseRunner:
    """Ejecuta fases del proyecto actual sin conservar historial entre llamadas."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def run(
        self,
        phase: str,
        spec_path: str | None,
        model_name: str,
        context_path: str | None = None,
    ) -> str:
        """Valida y ejecuta una fase, guardando su artefacto cuando corresponda."""
        self.validate_gates(phase, spec_path or "")

        phase_file = self._resolve_phase_file(phase)
        phase_kind = self._phase_kind(phase, phase_file)
        spec_file = Path(spec_path) if spec_path else None
        context_file = Path(context_path) if context_path else None

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

        context: str | None = None
        if context_file is not None:
            self._ensure_file(
                context_file,
                f"No se encontró el archivo de contexto: {context_file}",
            )
            context = self._read_file(context_file, "el contexto")

        graph_context = ""
        if phase_kind in {"spec", "goldfish"} and os.getenv(
            "GRAPHIFY_MCP_URL", ""
        ).strip():
            query_target = spec_file or context_file
            query = str(query_target) if query_target is not None else phase
            graph_context = fetch_graph_context(query)

        if phase_kind == "goldfish":
            self.console.print("Aislando Memoria para Goldfish", style="bold yellow")

        # La Memoria Caliente es siempre una lista local y nueva, sin historial.
        messages = self._build_messages(
            phase=phase,
            spec_path=spec_file,
            cold_memory=cold_memory,
            specification=specification,
            context=context,
            graph_context=graph_context,
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

        artifact_path = self._save_artifact(
            phase_kind, content, spec_file, context_file
        )
        if phase_kind == "goldfish":
            self._update_spec_metadata(spec_file, content, artifact_path)

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

    def _save_artifact(
        self,
        phase_kind: str,
        content: str,
        spec_path: Path | None,
        context_path: Path | None,
    ) -> Path | None:
        """Persiste la salida de la fase cuando produce un artefacto Markdown."""
        artifact_path = self._artifact_path(phase_kind, spec_path, context_path)
        if artifact_path is None:
            return None

        try:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ArtifactSaveError(
                f"No se pudo guardar el artefacto en {artifact_path}: {exc}"
            ) from exc

        self.console.print(
            f"✅ Guardado en {self._display_path(artifact_path)}",
            style="green",
            markup=False,
        )
        return artifact_path

    @staticmethod
    def _is_goldfish_phase(phase: str) -> bool:
        """Indica si la fase es una auditoría Goldfish (1b)."""
        normalized_phase = phase.lower()
        return "1b" in normalized_phase or "goldfish" in normalized_phase

    @classmethod
    def _phase_kind(cls, phase: str, phase_file: Path) -> str:
        """Clasifica la fase resuelta para aplicar su comportamiento."""
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
        """Calcula el destino del artefacto según el tipo de fase.

        Las fases TDD (2 o superior) producen salidas estructuradas, no un
        Markdown, por lo que todavía no generan archivo.
        """
        if phase_kind not in {"spec", "goldfish"}:
            return None

        spec_name = self._spec_name(spec_path, context_path)
        if spec_name is None:
            self.console.print(
                "⚠️ No se pudo determinar el nombre del spec; "
                "el artefacto no se guardó.",
                style="yellow",
            )
            return None

        specs_dir = Path.cwd() / "specs"
        if phase_kind == "spec":
            return specs_dir / f"{spec_name}.spec.md"

        audit_number = self._next_audit_number(specs_dir, spec_name)
        return specs_dir / f"{spec_name}.audit.{audit_number}.md"

    def _update_spec_metadata(
        self,
        spec_path: Path | None,
        audit_content: str,
        audit_path: Path | None,
    ) -> None:
        """Sincroniza el frontmatter del spec con el veredicto del Goldfish."""
        if spec_path is None:
            return

        if self._extract_verdict(audit_content) != "audited":
            self.console.print(
                "⚠️ Auditoría rechazada. El spec sigue en draft.",
                style="yellow",
                markup=False,
            )
            return

        if audit_path is None:
            self.console.print(
                "⚠️ No se pudo registrar la auditoría en el spec.",
                style="yellow",
                markup=False,
            )
            return

        specification = self._read_file(
            spec_path, "el spec para actualizar su frontmatter"
        )
        if self._split_frontmatter(specification) is None:
            self.console.print(
                "⚠️ El spec no tiene frontmatter; no se actualizó su estado.",
                style="yellow",
                markup=False,
            )
            return

        updated = self._set_frontmatter_field(
            specification,
            "status",
            "audited",
            only_if="draft",
        )
        updated = self._set_frontmatter_field(
            updated,
            "goldfish_audit",
            self._display_path(audit_path),
        )

        try:
            spec_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            raise ArtifactSaveError(
                f"No se pudo actualizar el spec {spec_path}: {exc}"
            ) from exc

        self.console.print(
            "✅ Spec actualizado a status: audited",
            style="green",
            markup=False,
        )

    @staticmethod
    def _extract_verdict(audit_content: str) -> str | None:
        """Extrae el veredicto final; effective_verdict prevalece sobre verdict."""
        verdicts: dict[str, str] = {}
        for match in _VERDICT_PATTERN.finditer(audit_content):
            verdicts[match.group("key").lower()] = match.group("verdict").lower()

        return verdicts.get("effective_verdict") or verdicts.get("verdict")

    @classmethod
    def _set_frontmatter_field(
        cls,
        content: str,
        field: str,
        value: str,
        *,
        only_if: str | None = None,
    ) -> str:
        """Reemplaza un campo del frontmatter preservando el resto del YAML."""
        parts = cls._split_frontmatter(content)
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
            new_body = body[: match.start()] + replacement + body[match.end() :]
        elif body.endswith(("\n", "\r")):
            new_body = f"{body}{field}: {value}\n"
        elif body:
            new_body = f"{body}\n{field}: {value}\n"
        else:
            new_body = f"{field}: {value}\n"

        return f"{opening}{new_body}{closing}"

    @staticmethod
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

    @staticmethod
    def _spec_name(spec_path: Path | None, context_path: Path | None) -> str | None:
        """Deriva el nombre base del spec a partir del spec o, si falta, del contexto."""
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
        """Devuelve el siguiente número de auditoría disponible para un spec."""
        if not specs_dir.is_dir():
            return 1

        audit_pattern = re.compile(
            rf"^{re.escape(spec_name)}\.audit\.(\d+)\.md$",
            re.IGNORECASE,
        )
        try:
            entries = list(specs_dir.iterdir())
        except OSError as exc:
            raise ArtifactSaveError(
                f"No se pudo inspeccionar el directorio de specs {specs_dir}: {exc}"
            ) from exc

        numbers = [
            int(match.group(1))
            for path in entries
            if path.is_file() and (match := audit_pattern.match(path.name))
        ]
        return max(numbers, default=0) + 1

    @staticmethod
    def _display_path(path: Path) -> str:
        """Muestra la ruta relativa al proyecto con separadores POSIX."""
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    @classmethod
    def _extract_frontmatter(cls, content: str) -> str:
        """Devuelve únicamente el frontmatter inicial, sin el cuerpo Markdown."""
        parts = cls._split_frontmatter(content)
        return parts[1] if parts is not None else ""

    @staticmethod
    def _resolve_phase_file(phase: str) -> Path:
        """Traduce un alias o nombre de fase al archivo de Memoria Fría."""
        normalized = phase.strip()
        if normalized.lower().endswith(".md"):
            normalized = normalized[:-3]

        if not normalized or not _PHASE_PATTERN.fullmatch(normalized):
            raise InputValidationError(
                "La fase solo puede contener letras, números, guiones y guiones bajos."
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
                    f"No se pudo leer el directorio de fases {skills_dir}: {exc}"
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
            f"No se encontró la Memoria Fría para la fase '{phase}' en {skills_dir}"
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
            raise InputValidationError(f"No se pudo leer {description} en {path}: {exc}") from exc

    @staticmethod
    def _build_messages(
        phase: str,
        spec_path: Path | None,
        cold_memory: str,
        specification: str | None,
        context: str | None = None,
        graph_context: str | None = None,
    ) -> list[dict[str, str]]:
        """Crea una lista nueva; nunca reutiliza ni extiende mensajes anteriores."""
        if spec_path is None:
            intro = (
                f"Ejecuta la fase '{phase}'.\n\n"
                "No se proporcionó una especificación de entrada para esta fase."
            )
        else:
            intro = f"Ejecuta la fase '{phase}' sobre la especificación '{spec_path}'."

        blocks: list[str] = []
        if context is not None:
            blocks.append(
                "--- INICIO DEL CONTEXTO ---\n"
                f"{context}\n"
                "--- FIN DEL CONTEXTO ---"
            )
        if graph_context:
            blocks.append(
                "--- INICIO DEL GRAFO DE CÓDIGO (Graphify MCP) ---\n"
                f"{graph_context}\n"
                "--- FIN DEL GRAFO DE CÓDIGO (Graphify MCP) ---"
            )
        if specification is not None:
            blocks.append(
                "--- INICIO DE LA ESPECIFICACIÓN ---\n"
                f"{specification}\n"
                "--- FIN DE LA ESPECIFICACIÓN ---"
            )

        user_content = "\n\n".join([intro, *blocks])

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
