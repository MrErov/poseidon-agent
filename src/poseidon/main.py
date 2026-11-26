"""Poseidón command-line interface."""

from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

from poseidon.config_manager import ConfigError, ConfigManager
from poseidon.console import configure_utf8_output
from poseidon.core import GateError, PhaseRunner, PoseidonError
from poseidon.herdr_delegator import HerdrDelegator

app = typer.Typer(
    name="poseidon",
    help="Deterministic execution engine for Keel Nav phases.",
    add_completion=False,
    no_args_is_help=True,
)
error_console = Console(stderr=True)


def _configure_utf8_output() -> None:
    """Avoid Unicode failures on legacy Windows consoles."""
    configure_utf8_output()


@app.callback()
def cli() -> None:
    """Orchestrate Keel Nav phases without keeping state between runs."""


@app.command("run")
def run_phase(
    phase: Annotated[
        str,
        typer.Option(
            "--phase",
            help="Phase or alias; for example: 1a, spec, 1b, goldfish, 2, tdd.",
        ),
    ],
    spec: Annotated[
        str | None,
        typer.Option(
            "--spec",
            help="Path to the spec Markdown; optional for Context Bootstrap and Phase 1a.",
        ),
    ] = None,
    context: Annotated[
        str | None,
        typer.Option(
            "--context",
            help="Path to a context Markdown; injected before the spec.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="LiteLLM model; required only when executor='api'.",
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
    debug: Annotated[
        bool,
        typer.Option(
            "--debug/--no-debug",
            help="Enable JSON-RPC and terminal debug output.",
        ),
    ] = False,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            help="Resume an existing Herdr terminal (for example, t19).",
        ),
    ] = None,
) -> None:
    """Execute a phase through LiteLLM or a local CLI."""
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
            "[red]--model is required when --executor=api.[/red]"
        )
        raise typer.Exit(code=1)

    try:
        herdr_delegator = (
            HerdrDelegator.from_settings(execution.herdr, debug=debug)
            if executor == "herdr"
            else None
        )
        runner = PhaseRunner(herdr_delegator=herdr_delegator)
        if resume is not None:
            if executor != "herdr":
                error_console.print(
                    "[bold red]Error:[/bold red] [red]--resume requires --executor herdr.[/red]"
                )
                raise typer.Exit(code=1)
            content = herdr_delegator.resume(resume)
            runner.console.print(Markdown(content))
            return
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
