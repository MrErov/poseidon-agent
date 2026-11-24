"""Excepciones compartidas de Poseidón."""

from __future__ import annotations


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


class IllegalTransitionError(PoseidonError):
    """Intento de transición de estado no permitida."""


class ConfigError(RuntimeError):
    """La configuración YAML es inválida o inconsistente."""


class ConfigValidationError(ConfigError):
    """Un valor de configuración tiene un tipo o formato inválido."""


class DelegationError(RuntimeError):
    """Un CLI local no pudo ejecutar el prompt o devolvió una salida inválida."""