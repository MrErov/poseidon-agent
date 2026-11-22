"""Interfaz de línea de comandos de Poseidón."""

import sys
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape

from poseidon.core import GateError, PhaseRunner, PoseidonError

app = typer.Typer(
    name="poseidon",
    help="Motor de ejecución determinista para las fases de Keel Nav.",
    add_completion=False,
    no_args_is_help=True,
)
error_console = Console(stderr=True)


def _configure_utf8_output() -> None:
    """Evita errores de consolas Windows heredadas con mensajes Unicode."""
    if sys.platform != "win32":
        return

    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("_", "-")
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding not in {"utf-8", "utf8"} and callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


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
        str,
        typer.Option(
            "--executor",
            help="Ejecutor: api, claude-code, codex u opencode.",
        ),
    ] = "api",
) -> None:
    """Ejecuta una fase mediante LiteLLM o un CLI local."""
    _configure_utf8_output()
    load_dotenv()
    if executor.strip().lower() == "api" and not (model and model.strip()):
        error_console.print(
            "[bold red]Error:[/bold red] "
            "[red]--model es obligatorio cuando --executor=api.[/red]"
        )
        raise typer.Exit(code=1)

    try:
        runner = PhaseRunner()
        runner.run(
            phase=phase,
            spec_path=spec,
            model_name=model,
            context_path=context,
            executor=executor,
        )
    except GateError as exc:
        error_console.print(str(exc), style="bold red", markup=False)
        raise typer.Exit(code=1) from None
    except PoseidonError as exc:
        error_console.print(f"[bold red]Error:[/bold red] [red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
