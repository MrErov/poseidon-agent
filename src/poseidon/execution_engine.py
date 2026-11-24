"""Motor de ejecución: llama a LiteLLM o delega a CLIs locales/Herdr."""

from __future__ import annotations

from typing import Any

import litellm

from poseidon.delegator import DelegationError, LocalCLIDelegator
from poseidon.exceptions import CompletionError, InputValidationError
from poseidon.herdr_delegator import HerdrDelegator
from poseidon.prompt_builder import PromptBuilder

_LOCAL_EXECUTORS = {"claude-code", "codex", "opencode"}


class ExecutionEngine:
    """Ejecuta la inferencia usando API (LiteLLM) o delegación local."""

    def __init__(
        self,
        console=None,
        delegator: LocalCLIDelegator | None = None,
        herdr_delegator: HerdrDelegator | None = None,
    ):
        self.console = console
        self.delegator = delegator or LocalCLIDelegator()
        self.herdr_delegator = herdr_delegator or HerdrDelegator()

    def execute(
        self,
        messages: list[dict[str, str]],
        executor: str,
        model_name: str | None = None,
        herdr_agent: str | None = None,
    ) -> str:
        """Ejecuta el prompt y retorna el contenido de la respuesta."""
        executor = executor.strip().lower()
        if executor != "api" and executor not in _LOCAL_EXECUTORS | {"herdr"}:
            raise InputValidationError(f"Executor no soportado: '{executor}'.")
        if executor == "api" and not (model_name and model_name.strip()):
            raise InputValidationError(
                "El parámetro --model es obligatorio cuando executor='api'."
            )

        if executor == "api":
            return self._execute_api(messages, model_name)
        else:
            prompt = PromptBuilder.format_for_cli(messages)
            return self._execute_delegator(prompt, executor, herdr_agent)

    def _execute_api(self, messages: list[dict[str, str]], model_name: str) -> str:
        try:
            response = litellm.completion(
                model=model_name,
                messages=messages,
                temperature=0.0,
                timeout=300,
            )
        except Exception as exc:
            raise CompletionError(
                f"No se pudo ejecutar con el modelo '{model_name}': {exc}"
            ) from exc
        return self._extract_content(response)

    def _execute_delegator(
        self, prompt: str, executor: str, herdr_agent: str | None
    ) -> str:
        try:
            if executor == "herdr":
                return self.herdr_delegator.execute(prompt, herdr_agent or "claude-code")
            else:
                return self.delegator.execute(prompt, executor)
        except DelegationError as exc:
            raise CompletionError(f"No se pudo ejecutar con '{executor}': {exc}") from exc

    @staticmethod
    def _extract_content(response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise CompletionError("Respuesta con formato inesperado.") from exc
        if not isinstance(content, str) or not content.strip():
            raise CompletionError("Respuesta vacía o sin contenido de texto.")
        return content