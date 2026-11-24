"""Textual interface for guided Keel Nav phase execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.console import Console
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog

from poseidon.config_manager import ConfigManager
from poseidon.core import PhaseRunner
from poseidon.herdr_delegator import HerdrDelegator

_PHASES = [
    ("0", "Phase 0 — Context Bootstrap"),
    ("1a", "Phase 1a — Spec Writer"),
    ("1b", "Phase 1b — Goldfish Audit"),
    ("2", "Phase 2 — Strict TDD"),
    ("3", "Phase 3 — ODD Vertical Slice"),
    ("4", "Phase 4 — Drift Control"),
]


class _MessageText:
    """Forward Rich Console writes as thread-safe Textual messages."""

    def __init__(self, app: PoseidonApp) -> None:
        self.app = app
        self.encoding = "utf-8"

    def write(self, text: str) -> int:
        if text:
            self.app.post_message(PoseidonApp.StreamText(text))
        return len(text)

    def flush(self) -> None:
        pass

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False


class PoseidonApp(App[None]):
    """Display phases and stream PhaseRunner output in a terminal UI."""

    CSS = """
    #main {
        height: 1fr;
    }
    #phases {
        width: 38;
        border: solid $primary;
    }
    #output {
        width: 1fr;
        border: solid $accent;
        padding: 1 2;
    }
    #input-panel {
        height: auto;
        padding: 1 2;
        border: solid $surface;
    }
    .input-row {
        height: 3;
        margin-bottom: 1;
    }
    .input-label {
        width: 12;
        content-align: right middle;
        padding-right: 1;
    }
    .section-title {
        text-style: bold;
    }
    """
    BINDINGS = [
        ("ctrl+r", "run_selected_phase", "Run phase"),
        ("ctrl+x", "cancel_phase", "Cancel"),
        ("ctrl+q", "quit", "Quit"),
    ]

    class StreamText(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class PhaseComplete(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()

    def __init__(
        self,
        runner_factory: Callable[..., Any] | None = None,
        config_resolver: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__()
        self.runner_factory = runner_factory
        self.config_resolver = config_resolver or (
            lambda phase: ConfigManager().resolve(phase)
        )
        self.output_text = ""
        self._phase_running = False
        self._current_worker = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with ListView(id="phases"):
                for phase_id, label in _PHASES:
                    yield ListItem(Label(label), id=f"phase-{phase_id}")
            with Vertical(id="output-panel"):
                with Vertical(id="input-panel"):
                    yield Label("Inputs", classes="section-title")
                    with Horizontal(classes="input-row"):
                        yield Label("Spec Path:", classes="input-label")
                        yield Input(placeholder="specs/US-001.spec.md", id="spec-input")
                    with Horizontal(classes="input-row"):
                        yield Label("Context Path:", classes="input-label")
                        yield Input(placeholder="docs/context/api.md", id="context-input")
                yield RichLog(id="output", markup=False, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "🔱 Poseidon Agent"
        self.sub_title = "Ready"
        self.query_one(ListView).index = 0
        self.query_one(RichLog).write("Select a phase, fill inputs, and press Ctrl+R.")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.sub_title = f"Selected {event.item.id.removeprefix('phase-')}"

    def action_run_selected_phase(self) -> None:
        if self._phase_running:
            return

        phases = self.query_one(ListView)
        selected = phases.highlighted_child
        phase = selected.id.removeprefix("phase-") if selected is not None else "0"

        spec_path = self.query_one("#spec-input", Input).value.strip() or None
        context_path = self.query_one("#context-input", Input).value.strip() or None

        self._phase_running = True
        self.sub_title = f"Running {phase}..."
        self.output_text = ""
        self.query_one(RichLog).clear()
        self._current_worker = self.run_worker(
            lambda: self._execute_phase(phase, spec_path, context_path),
            thread=True,
            exclusive=True,
        )

    def action_cancel_phase(self) -> None:
        """Cancel the currently running phase."""
        if self._phase_running and self._current_worker is not None:
            self._current_worker.cancel()
            self.post_message(self.StreamText("\n[bold yellow]Cancelled by user[/bold yellow]\n"))
            self.post_message(self.PhaseComplete("Cancelled"))

    def _execute_phase(self, phase: str, spec_path: str | None, context_path: str | None) -> None:
        try:
            execution = self.config_resolver(phase)
            console = Console(
                file=_MessageText(self),
                force_terminal=False,
                color_system=None,
            )
            herdr = None
            if execution.executor == "herdr":
                herdr = HerdrDelegator.from_settings(execution.herdr)
                # Override console so Herdr logs go through our adapter
                herdr.console = console

            runner = self._make_runner(console, herdr)
            runner.run(
                phase=phase,
                spec_path=spec_path,
                model_name=execution.model,
                context_path=context_path,
                executor=execution.executor,
                herdr_agent=execution.agent,
            )
            # NOTE: PhaseRunner already prints the result via console.print(Markdown(content))
            # so we don't re-post it here to avoid duplication
            self.post_message(self.PhaseComplete("Completed"))
        except Exception as exc:
            self.post_message(self.StreamText(f"\nError: {exc}\n"))
            self.post_message(self.PhaseComplete("Error"))

    def _make_runner(
        self,
        console: Console,
        herdr: HerdrDelegator | None,
    ) -> Any:
        if self.runner_factory is not None:
            return self.runner_factory(console=console, herdr_delegator=herdr)
        return PhaseRunner(console=console, herdr_delegator=herdr)

    def on_poseidon_app_stream_text(self, message: StreamText) -> None:
        self.output_text += message.text
        self.query_one(RichLog).write(message.text)

    def on_poseidon_app_phase_complete(self, message: PhaseComplete) -> None:
        self._phase_running = False
        self._current_worker = None
        self.sub_title = message.status

    def action_quit(self) -> None:
        if self._phase_running and self._current_worker is not None:
            self._current_worker.cancel()
        self.exit()
