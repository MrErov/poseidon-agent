"""Interfaz de línea de comandos de Poseidón."""

from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape

from poseidon.config_manager import ConfigError, ConfigManager
from poseidon.console import configure_utf8_output
from poseidon.core import GateError, PhaseRunner, PoseidonError
from poseidon.herdr_delegator import HerdrDelegator

app = typer.Typer(
    name="poseidon",
    help="Motor de ejecución determinista para las fases de Keel Nav.",
    add_completion=False,
    no_args_is_help=True,
)
error_console = Console(stderr=True)


def _configure_utf8_output() -> None:
    """Evita errores de consolas Windows heredadas con mensajes Unicode."""
    configure_utf8_output()


@app.callback()
def cli() -> None:
    """Orquesta fases de Keel Nav sin mantener estado entre ejecuciones."""


@app.command("run")
def run_phase(
    phase: Annotated[
        str,
        typer.Option(
            "--phase",
            help="Fase o alias; por ejemplo: 1a, spec, 1b, goldfish, 2, tdd.",
        ),
    ],
    spec: Annotated[
        str | None,
        typer.Option(
            "--spec",
            help="Ruta al spec Markdown; opcional para Context Bootstrap y la Fase 1a.",
        ),
    ] = None,
    context: Annotated[
        str | None,
        typer.Option(
            "--context",
            help="Ruta a un Markdown de contexto; se inyecta antes del spec.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Modelo de LiteLLM; obligatorio solo cuando executor='api'.",
        ),
    ] = None,
    executor: Annotated[
        str | None,
        typer.Option(
            "--executor",
            help="Executor: api, claude-code, codex, opencode, or herdr.",
        ),
    ] = None,
    role: Annotated[
        str | None,
        typer.Option("--role", help="Agent role from config.yaml."),
    ] = None,
    herdr_agent: Annotated[
        str | None,
        typer.Option("--herdr-agent", help="Agent used when executor is herdr."),
    ] = None,
) -> None:
    """Ejecuta una fase mediante LiteLLM o un CLI local."""
    _configure_utf8_output()
    load_dotenv()
    try:
        execution = ConfigManager().resolve(
            phase=phase,
            role=role,
            cli_executor=executor,
            cli_model=model,
        )
    except ConfigError as exc:
        error_console.print(f"[bold red]Configuration error:[/bold red] {escape(str(exc))}")
        raise typer.Exit(code=1) from None

    executor = execution.executor
    model = execution.model
    selected_herdr_agent = herdr_agent or execution.agent
    if executor == "api" and not (model and model.strip()):
        error_console.print(
            "[bold red]Error:[/bold red] "
            "[red]--model es obligatorio cuando --executor=api.[/red]"
        )
        raise typer.Exit(code=1)

    try:
        herdr_delegator = (
            HerdrDelegator.from_settings(execution.herdr)
            if executor == "herdr"
            else None
        )
        runner = PhaseRunner(herdr_delegator=herdr_delegator)
        runner.run(
            phase=phase,
            spec_path=spec,
            model_name=model,
            context_path=context,
            executor=executor,
            herdr_agent=selected_herdr_agent,
        )
    except GateError as exc:
        error_console.print(str(exc), style="bold red", markup=False)
        raise typer.Exit(code=1) from None
    except PoseidonError as exc:
        error_console.print(f"[bold red]Error:[/bold red] [red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from None


@app.command("tui")
def tui_command() -> None:
    """Launch the interactive Textual interface."""
    from poseidon.tui import PoseidonApp

    PoseidonApp().run()


if __name__ == "__main__":
    app()
