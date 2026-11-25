"""Poseidon Agent: orquestador determinista para Keel Nav."""

from poseidon.config_manager import (
    ConfigError,
    ConfigManager,
    ConfigValidationError,
    ExecutionConfig,
)
from poseidon.core import PhaseRunner
from poseidon.exceptions import (
    ArtifactSaveError,
    CompletionError,
    DelegationError,
    GateError,
    IllegalTransitionError,
    InputValidationError,
    PoseidonError,
)
from poseidon.exceptions import (
    ConfigError as ConfigErrorAlias,
)
from poseidon.exceptions import (
    ConfigValidationError as ConfigValidationErrorAlias,
)
from poseidon.execution_engine import ExecutionEngine
from poseidon.prompt_builder import PromptBuilder
from poseidon.spec_state_machine import SpecStateMachine

__version__ = "3.5.0"

__all__ = [
    "__version__",
    "PhaseRunner",
    "SpecStateMachine",
    "PromptBuilder",
    "ExecutionEngine",
    "ConfigManager",
    "ConfigError",
    "ConfigValidationError",
    "ExecutionConfig",
    "PoseidonError",
    "InputValidationError",
    "GateError",
    "CompletionError",
    "ArtifactSaveError",
    "IllegalTransitionError",
    "DelegationError",
    "ConfigErrorAlias",
    "ConfigValidationErrorAlias",
]