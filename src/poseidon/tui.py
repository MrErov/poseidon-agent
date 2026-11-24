"""Textual interface for guided Keel Nav phase execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.console import Console
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Footer, Header, Label, ListItem, ListView, RichLog

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
    """
    BINDINGS = [
        ("ctrl+r", "run_selected_phase", "Run phase"),
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with ListView(id="phases"):
                for phase_id, label in _PHASES:
                    yield ListItem(Label(label), id=f"phase-{phase_id}")
            yield RichLog(id="output", markup=True, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "🔱 Poseidon Agent"
        self.sub_title = "Ready"
        self.query_one(ListView).index = 0
        self.query_one(RichLog).write("Select a phase and press Ctrl+R.")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.sub_title = f"Selected {event.item.id.removeprefix('phase-')}"

    def action_run_selected_phase(self) -> None:
        if self._phase_running:
            return

        phases = self.query_one(ListView)
        selected = phases.highlighted_child
        phase = selected.id.removeprefix("phase-") if selected is not None else "0"
        self._phase_running = True
        self.sub_title = f"Running {phase}..."
        self.output_text = ""
        self.query_one(RichLog).clear()
        self.run_worker(
            lambda: self._execute_phase(phase),
            thread=True,
            exclusive=True,
        )

    def _execute_phase(self, phase: str) -> None:
        try:
            execution = self.config_resolver(phase)
            console = Console(
                file=_MessageText(self),
                force_terminal=False,
                color_system=None,
            )
            herdr = (
                HerdrDelegator.from_settings(execution.herdr)
                if execution.executor == "herdr"
                else None
            )
            runner = self._make_runner(console, herdr)
            result = runner.run(
                phase=phase,
                spec_path=None,
                model_name=execution.model,
                context_path=None,
                executor=execution.executor,
                herdr_agent=execution.agent,
            )
            if result:
                self.post_message(self.StreamText(f"\n{result}\n"))
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
        self.sub_title = message.status

    def action_quit(self) -> None:
        self.exit()
