"""Poseidón command-line interface."""

from pathlib import Path
from typing import Annotated

import questionary
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table

from poseidon.config_manager import ConfigError, ConfigManager
from poseidon.console import configure_utf8_output
from poseidon.core import GateError, PhaseRunner, PoseidonError
from poseidon.herdr_delegator import HerdrDelegator
from poseidon.spec_state_machine import SpecStateMachine

app = typer.Typer(
    name="poseidon",
    help="Deterministic execution engine for Keel Nav phases.",
    add_completion=False,
    no_args_is_help=True,
)
error_console = Console(stderr=True)

_PHASES: tuple[tuple[str, str, str], ...] = (
    ("0", "Context Bootstrap", "00-context-bootstrap.md"),
    ("1a", "Spec Writer", "01-sdd-spec-writer.md"),
    ("1b", "Goldfish Audit", "02-egm-goldfish-audit.md"),
    ("2", "TDD Cycle", "03-tdd-cycle.md"),
    ("3", "ODD Vertical Slice", "04-odd-vertical-slice.md"),
    ("4", "Drift Control", "05-drift-control.md"),
)
_SPEC_PHASES = {"1b", "2", "3", "4"}
_WIZARD_ROLES = ("architect", "tester")


def _configure_utf8_output() -> None:
    """Avoid Unicode failures on legacy Windows consoles."""
    configure_utf8_output()


def _display_path(path: Path) -> str:
    """Return a repository-relative POSIX path when possible."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _discover_specs() -> list[Path]:
    """Return every ``*.spec.md`` file in the local specs directory."""
    specs_dir = Path.cwd() / "specs"
    if not specs_dir.is_dir():
        return []
    return sorted(specs_dir.glob("*.spec.md"), key=lambda path: path.name.lower())


def _resolve_spec_default(spec: str | None, console: Console) -> str | None:
    """Use the only available spec when --spec was omitted."""
    if spec:
        return spec
    candidates = _discover_specs()
    if len(candidates) != 1:
        return None
    detected = _display_path(candidates[0])
    console.print(f"ℹ️ Auto-detectado spec: {detected}", markup=False)
    return detected


def _ask_question(question) -> object:
    """Ask a questionary prompt and abort cleanly when it is cancelled."""
    answer = question.ask()
    if answer is None:
        error_console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(code=1)
    return answer


def _wizard_defaults(
    phase: str | None,
    spec: str | None,
    role: str | None,
) -> tuple[str, str | None, str]:
    """Collect phase, spec, and role for the interactive run wizard."""
    phase_choices = [
        questionary.Choice(f"{phase_id} — {label}", value=phase_id)
        for phase_id, label, _ in _PHASES
    ]
    default_phase = phase if any(phase_id == phase for phase_id, _, _ in _PHASES) else None
    selected_phase = str(
        _ask_question(
            questionary.select("Phase:", choices=phase_choices, default=default_phase)
        )
    )

    selected_spec: str | None = None
    if selected_phase in _SPEC_PHASES:
        candidates = _discover_specs()
        if candidates:
            choices = [_display_path(path) for path in candidates]
            if spec and spec in choices:
                default_spec = spec
            else:
                default_spec = choices[0] if len(choices) == 1 else None
            selected_spec = str(
                _ask_question(
                    questionary.select("Spec:", choices=choices, default=default_spec)
                )
            )
        else:
            selected_spec = str(
                _ask_question(questionary.text("Spec path:"))
            ).strip()
            if not selected_spec:
                error_console.print(
                    "[bold red]Error:[/bold red] [red]A spec path is required "
                    "for this phase.[/red]"
                )
                raise typer.Exit(code=1)

    try:
        configured_default = ConfigManager().default_role
    except ConfigError:
        configured_default = ConfigManager.DEFAULT_ROLE
    default_role = (
        role
        if role in _WIZARD_ROLES
        else configured_default
        if configured_default in _WIZARD_ROLES
        else "tester"
    )
    selected_role = str(
        _ask_question(
            questionary.select("Role:", choices=list(_WIZARD_ROLES), default=default_role)
        )
    )
    return selected_phase, selected_spec, selected_role


@app.callback()
def cli() -> None:
    """Orchestrate Keel Nav phases without keeping state between runs."""


@app.command("run")
def run_phase(
    phase: Annotated[
        str | None,
        typer.Option(
            "--phase",
            help="Phase or alias; for example: 1a, spec, 1b, goldfish, 2, tdd.",
        ),
    ] = None,
    spec: Annotated[
        str | None,
        typer.Option(
            "--spec",
            help="Path to the spec Markdown; auto-detected when only one exists.",
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
    interactive: Annotated[
        bool,
        typer.Option(
            "-i",
            "--interactive",
            help="Launch the interactive wizard to choose phase, spec, and role.",
        ),
    ] = False,
) -> None:
    """Execute a phase through LiteLLM or a local CLI."""
    _configure_utf8_output()
    load_dotenv()

    if resume is not None and not phase:
        phase = "0"
    elif interactive or not phase:
        phase, spec, role = _wizard_defaults(phase, spec, role)

    console = Console()
    spec = _resolve_spec_default(spec, console)

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


@app.command("status")
def status_command() -> None:
    """Show phases, spec statuses, and the default role."""
    _configure_utf8_output()

    try:
        default_role = ConfigManager().default_role
    except ConfigError as exc:
        error_console.print(f"[bold red]Configuration error:[/bold red] {escape(str(exc))}")
        raise typer.Exit(code=1) from None

    table = Table(title="🔱 Poseidon Status", show_header=True, header_style="bold cyan")
    table.add_column("Type", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Detail")

    table.add_row("Default role", default_role, "used when --role is omitted")

    skills_dir = Path.cwd() / ".meta-skills"
    for phase_id, label, skill_file in _PHASES:
        skill_exists = (skills_dir / skill_file).is_file()
        table.add_row(
            "Phase",
            f"{phase_id} — {label}",
            "ready" if skill_exists else "missing cold memory",
        )

    specs = _discover_specs()
    if not specs:
        table.add_row("Spec", "—", "no specs found")
    state_machine = SpecStateMachine()
    for spec_path in specs:
        try:
            spec_status = state_machine.read_status(spec_path).value
        except (PoseidonError, OSError):
            spec_status = "unknown"
        table.add_row("Spec", _display_path(spec_path), spec_status)

    Console().print(table)


@app.command("tui")
def tui_command() -> None:
    """Launch the interactive Textual interface."""
    from poseidon.tui import PoseidonApp

    PoseidonApp().run()


if __name__ == "__main__":
    app()
