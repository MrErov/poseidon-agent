"""Poseidón command-line interface."""

import os
import shutil
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
from poseidon.mcp_manager import (
    get_config_paths,
    list_all_mcps,
    sync_mcp,
)
from poseidon.spec_state_machine import SpecStateMachine
from poseidon.utils import get_working_dir
from poseidon.version import get_version

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


# MCP command group
mcp_app = typer.Typer(
    name="mcp",
    help="Manage MCP (Model Context Protocol) servers across agents.",
    add_completion=False,
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("list")
def mcp_list() -> None:
    """List all MCP servers configured across agents."""
    _configure_utf8_output()

    mcps = list_all_mcps()
    if not mcps:
        Console().print("[yellow]No MCP servers found.[/yellow]")
        return

    table = Table(title="📡 MCP Registry", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Command", style="green", max_width=40)
    table.add_column("Args", style="yellow", max_width=50)
    table.add_column("Status", justify="center")

    for mcp in mcps:
        args_str = " ".join(mcp.get("args", []))
        if len(args_str) > 50:
            args_str = args_str[:47] + "..."

        status = "🔴 Disabled" if mcp.get("disabled") else "🟢 Enabled"
        agent_display = mcp["agent"].replace("_alt", " (alt)")

        table.add_row(
            mcp["name"],
            agent_display,
            mcp.get("command", "")[:40],
            args_str,
            status,
        )

    Console().print(table)


@mcp_app.command("sync")
def mcp_sync(
    mcp_name: Annotated[str, typer.Argument(help="Name of the MCP server to sync.")],
    from_agent: Annotated[
        str,
        typer.Option("--from", help="Source agent (opencode, codex, claude)."),
    ],
    to_agent: Annotated[
        str,
        typer.Option("--to", help="Target agent (opencode, codex, claude)."),
    ],
) -> None:
    """Sync an MCP server from one agent to another."""
    _configure_utf8_output()

    config_paths = get_config_paths()
    valid_agents = ["opencode", "codex", "claude"]

    if from_agent not in valid_agents or to_agent not in valid_agents:
        error_console.print(
            f"[bold red]Error:[/bold red] Invalid agent. Valid: {', '.join(valid_agents)}"
        )
        raise typer.Exit(code=1)

    try:
        success = sync_mcp(mcp_name, from_agent, to_agent, config_paths)
    except ValueError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if success:
        Console().print(
            f"[green]✅[/green] Synced '[bold]{mcp_name}[/bold]' "
            f"from [cyan]{from_agent}[/cyan] to [cyan]{to_agent}[/cyan]"
        )
    else:
        error_console.print(
            f"[bold red]Error:[/bold red] MCP '[bold]{mcp_name}[/bold]' not found in {from_agent}"
        )
        raise typer.Exit(code=1)


def _configure_utf8_output() -> None:
    """Avoid Unicode failures on legacy Windows consoles."""
    configure_utf8_output()


def _display_path(path: Path) -> str:
    """Return a repository-relative POSIX path when possible."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _version_callback(value: bool) -> None:
    """Print the version and exit before any command runs."""
    if not value:
        return
    typer.echo(f"poseidon {get_version()}")
    raise typer.Exit()


def _discover_specs() -> list[Path]:
    """Return every ``*.spec.md`` file in the local specs directory."""
    specs_dir = get_working_dir() / "specs"
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
    console.print(f"ℹ️ Auto-detected spec: {detected}", markup=False)
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
def cli(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the Poseidon version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
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
            help="Resume a previous session (Herdr terminal ID or API session file).",
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
        config_manager = ConfigManager()
        model_routing = config_manager.get_model_routing()
        runner = PhaseRunner(herdr_delegator=herdr_delegator, model_routing=model_routing)
        if resume is not None:
            if executor == "herdr":
                content = herdr_delegator.resume(resume)
                runner.console.print(Markdown(content))
                return
            elif executor == "api":
                # API session resume - delegate to PhaseRunner with session file
                runner.run(
                    phase=phase,
                    spec_path=spec,
                    model_name=model,
                    context_path=context,
                    executor=executor,
                    herdr_agent=selected_herdr_agent,
                    resume_session=resume,
                )
                return
            else:
                error_console.print(
                    "[bold red]Error:[/bold red] "
                    "[red]--resume only supported for herdr and api executors.[/red]"
                )
                raise typer.Exit(code=1)
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

    skills_dir = get_working_dir() / ".meta-skills"
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


@app.command("doctor")
def doctor_command() -> None:
    """Check environment health and report readiness."""
    _configure_utf8_output()
    load_dotenv()

    console = Console()
    table = Table(
        title="🩺 Poseidon Environment Doctor",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    all_ok = True

    # 1. .meta-skills directory
    working_dir = get_working_dir()
    meta_skills_dir = working_dir / ".meta-skills"
    if meta_skills_dir.is_dir():
        # Check for at least some skill files
        skill_files = list(meta_skills_dir.glob("*.md"))
        if skill_files:
            table.add_row(
                ".meta-skills/",
                "[green]✅[/green]",
                f"Found {len(skill_files)} skill file(s)",
            )
        else:
            table.add_row(
                ".meta-skills/",
                "[yellow]⚠️[/yellow]",
                "Directory exists but no .md skill files found",
            )
            all_ok = False
    else:
        table.add_row(
            ".meta-skills/",
            "[red]❌[/red]",
            f"Missing at {meta_skills_dir}",
        )
        all_ok = False

    # 2. templates/ directory (optional but recommended)
    templates_dir = working_dir / "templates"
    if templates_dir.is_dir():
        table.add_row(
            "templates/",
            "[green]✅[/green]",
            "Template directory found",
        )
    else:
        table.add_row(
            "templates/",
            "[dim]ℹ️[/dim]",
            "Optional: not found (some phases may need it)",
        )

    # 3. config.yaml
    config_path = working_dir / "config.yaml"
    if config_path.is_file():
        try:
            cm = ConfigManager(config_path)
            _ = cm.default_role  # triggers validation
            table.add_row(
                "config.yaml",
                "[green]✅[/green]",
                "Valid configuration loaded",
            )
        except ConfigError as exc:
            table.add_row(
                "config.yaml",
                "[red]❌[/red]",
                f"Invalid: {exc}",
            )
            all_ok = False
    else:
        table.add_row(
            "config.yaml",
            "[yellow]⚠️[/yellow]",
            "Not found (will use defaults)",
        )

    # 4. Herdr CLI (hc)
    hc_path = shutil.which("hc")
    if hc_path:
        table.add_row(
            "hc (Herdr CLI)",
            "[green]✅[/green]",
            f"Found at {hc_path}",
        )
    else:
        table.add_row(
            "hc (Herdr CLI)",
            "[red]❌[/red]",
            "Not in PATH (required for --executor herdr)",
        )
        all_ok = False

    # 5. API Keys
    api_keys = {
        "NVIDIA_NIM_API_KEY": "NVIDIA NIM",
        "OPENAI_API_KEY": "OpenAI",
        "ANTHROPIC_API_KEY": "Anthropic",
    }
    for env_var, label in api_keys.items():
        if os.environ.get(env_var):
            table.add_row(
                f"{label} API Key",
                "[green]✅[/green]",
                f"{env_var} is set",
            )
        else:
            table.add_row(
                f"{label} API Key",
                "[yellow]⚠️[/yellow]",
                f"{env_var} not set (needed for API executor)",
            )

    console.print(table)
    console.print()

    if all_ok:
        console.print(
            "[bold green]🎉 Your environment is ready for Poseidon![/bold green]"
        )
    else:
        console.print(
            "[bold red]⚠️ Please fix the issues above before running Poseidon.[/bold red]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
