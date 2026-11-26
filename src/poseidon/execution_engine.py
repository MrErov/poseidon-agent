"""Execution engine: calls LiteLLM or delegates to local CLIs/Herdr."""

from __future__ import annotations

import threading
from typing import Any

import litellm

from poseidon.delegator import DelegationError, LocalCLIDelegator
from poseidon.exceptions import CompletionError, InputValidationError
from poseidon.herdr_delegator import HerdrDelegator
from poseidon.prompt_builder import PromptBuilder

_LOCAL_EXECUTORS = {"claude-code", "codex", "opencode"}


class ExecutionEngine:
    """Run inference through the API (LiteLLM) or local delegation."""

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
        phase_kind: str | None = None,
        artifact_path: Any = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Execute the prompt and return the response content.

        Args:
            cancel_event: Optional threading.Event to signal cooperative cancellation.
        """
        executor = executor.strip().lower()
        if executor != "api" and executor not in _LOCAL_EXECUTORS | {"herdr"}:
            raise InputValidationError(f"Unsupported executor: '{executor}'.")
        if executor == "api" and not (model_name and model_name.strip()):
            raise InputValidationError(
                "The --model parameter is required when executor='api'."
            )
        if cancel_event is not None and cancel_event.is_set():
            raise InputValidationError("Execution cancelled.")

        if executor == "api":
            return self._execute_api(messages, model_name, cancel_event)
        else:
            prompt = PromptBuilder.format_for_cli(messages)
            return self._execute_delegator(
                prompt,
                executor,
                herdr_agent,
                model_name,
                phase_kind=phase_kind,
                artifact_path=artifact_path,
                cancel_event=cancel_event,
            )

    def _execute_api(
        self,
        messages: list[dict[str, str]],
        model_name: str,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event is not None and cancel_event.is_set():
            raise InputValidationError("Execution cancelled before API call.")
        try:
            response = litellm.completion(
                model=model_name,
                messages=messages,
                temperature=0.0,
                timeout=300,
            )
        except Exception as exc:
            raise CompletionError(
                f"Could not run with model '{model_name}': {exc}"
            ) from exc
        return self._extract_content(response)

    def _execute_delegator(
        self,
        prompt: str,
        executor: str,
        herdr_agent: str | None,
        model_name: str | None = None,
        phase_kind: str | None = None,
        artifact_path: Any = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        try:
            if executor == "herdr":
                return self.herdr_delegator.execute(
                    prompt,
                    herdr_agent or "claude-code",
                    phase_kind=phase_kind,
                    artifact_path=artifact_path,
                    cancel_event=cancel_event,
                )
            else:
                return self.delegator.execute(prompt, executor, model=model_name)
        except DelegationError as exc:
            raise CompletionError(f"Could not execute with '{executor}': {exc}") from exc

    @staticmethod
    def _extract_content(response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise CompletionError("Unexpected response format.") from exc
        if not isinstance(content, str) or not content.strip():
            raise CompletionError("Empty response or no text content.")
        return content