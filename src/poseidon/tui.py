"""Textual interface for guided Keel Nav phase execution."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import CancelledError
from typing import Any

from rich.console import Console
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RichLog,
    Select,
    Static,
)

from poseidon.config_manager import ConfigManager
from poseidon.core import PhaseRunner
from poseidon.herdr_delegator import HerdrDelegator
from poseidon.model_router import PHASE_TO_ROLE, ModelRouter, ModelRouting

_PHASES = [
    ("0", "Phase 0 — Context Bootstrap"),
    ("1a", "Phase 1a — Spec Writer"),
    ("1b", "Phase 1b — Goldfish Audit"),
    ("2", "Phase 2 — Strict TDD"),
    ("3", "Phase 3 — ODD Vertical Slice"),
    ("4", "Phase 4 — Drift Control"),
]

# Breakpoints keep the layout honest from 80x24 up to ultra-wide terminals.
_NARROW_WIDTH = 72
_TINY_WIDTH = 40
_TINY_HEIGHT = 12


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
    Screen {
        background: $background;
        color: $text;
    }
    #main {
        height: 1fr;
        padding: 0 1;
    }
    #sidebar {
        width: 34;
        padding: 0 1 0 0;
    }
    #phases {
        height: 1fr;
        padding: 1;
        border: round $primary;
        background: $surface;
    }
    #phases:focus {
        border: round $accent;
    }
    #content {
        width: 1fr;
    }
    #input-panel {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }
    #phase-select-row {
        display: none;
    }
    #phase-select {
        width: 1fr;
    }
    .input-row {
        height: 3;
        margin-bottom: 1;
    }
    .input-label {
        width: 14;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    .section-title {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }
    #activity-bar {
        height: 1;
        padding: 0 1;
        margin-bottom: 1;
    }
    #spinner {
        display: none;
        width: 2;
        height: 1;
        color: $accent;
    }
    #activity-label {
        width: 1fr;
        color: $text-muted;
    }
    #activity-label.running {
        color: $accent;
    }
    #activity-label.success {
        color: $success;
    }
    #activity-label.warning {
        color: $warning;
    }
    #activity-label.error {
        color: $error;
    }
    #output {
        height: 1fr;
        padding: 0 1;
        border: round $primary;
        background: $surface;
    }
    #too-small {
        display: none;
        width: 1fr;
        height: 1fr;
        padding: 2 4;
        content-align: center middle;
        color: $text-muted;
    }
    Screen.narrow #sidebar {
        display: none;
    }
    Screen.narrow #phase-select-row {
        display: block;
    }
    Screen.tiny #main {
        display: none;
    }
    Screen.tiny #too-small {
        display: block;
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
        model_routing: ModelRouting | None = None,
    ) -> None:
        super().__init__()
        self.runner_factory = runner_factory
        self.config_resolver = config_resolver or (
            lambda phase: ConfigManager().resolve(phase)
        )
        self.model_router = model_routing if model_routing is not None else ModelRouter(
            ModelRouting(
                planner="nvidia_nim/nemotron-3-ultra-550b-a55b",
                coder="nvidia_nim/nemotron-3-ultra-550b-a55b",
                reviewer="nvidia_nim/nemotron-3-ultra-550b-a55b",
                default="nvidia_nim/nemotron-3-ultra-550b-a55b",
            )
        )
        self.output_text = ""
        self._phase_running = False
        self._current_worker = None
        self._selected_phase = "0"
        self._cancel_event: threading.Event | None = None
        self._updating_model_select = False

    @property
    def selected_phase(self) -> str:
        """Return the phase that Ctrl+R will run."""
        return self._selected_phase

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Terminal too small\n\n"
            "Resize to at least 40 columns x 12 rows to use Poseidon.",
            id="too-small",
        )
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Label("PHASES", classes="section-title")
                with ListView(id="phases"):
                    for phase_id, label in _PHASES:
                        yield ListItem(Label(label), id=f"phase-{phase_id}")
            with Vertical(id="content"):
                with Vertical(id="input-panel"):
                    yield Label("RUN CONFIGURATION", classes="section-title")
                    with Horizontal(classes="input-row", id="phase-select-row"):
                        yield Label("Phase:", classes="input-label")
                        yield Select(
                            [(label, phase_id) for phase_id, label in _PHASES],
                            value="0",
                            allow_blank=False,
                            id="phase-select",
                        )
                    with Horizontal(classes="input-row"):
                        yield Label("Model:", classes="input-label")
                        yield Select(
                            [
                                ("Planner (Phases 0,1a,3,4)", "planner"),
                                ("Coder (Phase 2)", "coder"),
                                ("Reviewer (Phase 1b)", "reviewer"),
                                ("Default", "default"),
                            ],
                            value="planner",
                            allow_blank=False,
                            id="model-select",
                        )
                    with Horizontal(classes="input-row"):
                        yield Label("Spec Path:", classes="input-label")
                        yield Input(
                            placeholder="specs/US-001.spec.md",
                            id="spec-input",
                        )
                    with Horizontal(classes="input-row"):
                        yield Label("Context Path:", classes="input-label")
                        yield Input(
                            placeholder="docs/context/api.md",
                            id="context-input",
                        )
                with Horizontal(id="activity-bar"):
                    yield LoadingIndicator(id="spinner")
                    yield Label("● Ready", id="activity-label")
                yield RichLog(id="output", markup=False, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "🔱 Poseidon Agent"
        self.sub_title = "Ready"
        self._selected_phase = "0"

        phases = self.query_one(ListView)
        phases.index = 0
        self.query_one(RichLog).write(
            "Welcome to Poseidon.\n\n"
            "1. Select a phase on the left.\n"
            "2. Fill in the spec and context paths.\n"
            "3. Press Ctrl+R to run, Ctrl+X to cancel, Ctrl+Q to quit."
        )
        self._apply_responsive_layout(
            self.screen.size.width, self.screen.size.height
        )
        self._set_activity("idle", "● Ready")
        if self.screen.has_class("narrow"):
            self.query_one("#phase-select", Select).focus()
        else:
            phases.focus()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive_layout(event.size.width, event.size.height)

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        """Switch between the full, compact, and minimum-size layouts."""
        narrow = width < _NARROW_WIDTH
        tiny = width < _TINY_WIDTH or height < _TINY_HEIGHT
        self.screen.set_class(narrow, "narrow")
        self.screen.set_class(tiny, "tiny")

    def _set_activity(self, state: str, text: str) -> None:
        """Update the spinner and the symbolic status label together."""
        try:
            spinner = self.query_one("#spinner", LoadingIndicator)
            label = self.query_one("#activity-label", Label)
        except NoMatches:
            # A late worker message may arrive while the app is unmounting.
            return
        spinner.display = state == "running"
        for name in ("running", "success", "warning", "error"):
            label.remove_class(name)
        if state in {"running", "success", "warning", "error"}:
            label.add_class(state)
        label.update(text)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if item is None or not item.id or not item.id.startswith("phase-"):
            return
        self._selected_phase = item.id.removeprefix("phase-")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item is None or not item.id or not item.id.startswith("phase-"):
            return
        self._selected_phase = item.id.removeprefix("phase-")
        self.sub_title = f"Selected {self._selected_phase}"

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "phase-select":
            if not isinstance(event.value, str):
                return
            if event.value == self._selected_phase:
                return
            self._selected_phase = event.value
            self.sub_title = f"Selected {self._selected_phase}"
            # Auto-select model based on phase
            role = PHASE_TO_ROLE.get(self._selected_phase, "planner")
            model_select = self.query_one("#model-select", Select)
            # Temporarily disconnect the model-select's on_select_changed handler
            model_select.value = role
            return

        if event.select.id != "model-select" or not isinstance(event.value, str):
            return
        # Model selection changed - don't update sub_title to avoid overriding phase selection
        # The sub_title should reflect the selected phase, not the model

    def action_run_selected_phase(self) -> None:
        if self._phase_running:
            return

        phase = self._selected_phase
        spec_path = self.query_one("#spec-input", Input).value.strip() or None
        context_path = self.query_one("#context-input", Input).value.strip() or None
        model_role = self.query_one("#model-select", Select).value
        model_name = self.model_router.resolve(phase, model_role)

        self._phase_running = True
        self._cancel_event = threading.Event()
        self.sub_title = f"Running {phase}..."
        self.output_text = ""
        self.query_one(RichLog).clear()
        self._set_activity("running", f"Running phase {phase}...")
        self._current_worker = self.run_worker(
            lambda: self._execute_phase(phase, spec_path, context_path, model_name=model_name),
            thread=True,
            exclusive=True,
        )

    def action_cancel_phase(self) -> None:
        """Cancel the currently running phase."""
        if self._phase_running and self._current_worker is not None:
            # Signal cooperative cancellation
            if self._cancel_event is not None:
                self._cancel_event.set()
            # If using Herdr, also kill the terminal
            herdr = getattr(self, "_last_herdr", None)
            if herdr is not None and herdr.last_terminal_address:
                try:
                    herdr.kill_terminal(herdr.last_terminal_address)
                except Exception:
                    pass  # Best effort
            self._current_worker.cancel()
            self.post_message(self.StreamText("\nCancelled by user\n"))
            self.post_message(self.PhaseComplete("Cancelled"))

    def _execute_phase(
        self,
        phase: str,
        spec_path: str | None,
        context_path: str | None,
        model_name: str | None = None,
    ) -> None:
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
                # Store for potential kill on cancellation
                self._last_herdr = herdr

            runner = self._make_runner(console, herdr)
            runner.run(
                phase=phase,
                spec_path=spec_path,
                model_name=model_name,
                context_path=context_path,
                executor=execution.executor,
                herdr_agent=execution.agent,
                cancel_event=self._cancel_event,
            )
            # NOTE: PhaseRunner already prints the result via console.print(Markdown(content))
            # so we don't re-post it here to avoid duplication
            self.post_message(self.PhaseComplete("Completed"))
        except (CancelledError, asyncio.CancelledError):
            # Worker was cancelled; action_cancel_phase already posted PhaseComplete("Cancelled")
            return
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
        # Pass model_router for multi-model orchestration
        return PhaseRunner(
            console=console,
            herdr_delegator=herdr,
            model_router=self.model_router,
        )

    def on_poseidon_app_stream_text(self, message: StreamText) -> None:
        self.output_text += message.text
        try:
            self.query_one(RichLog).write(message.text)
        except NoMatches:
            # The app may be shutting down while the worker flushes output.
            pass

    def on_poseidon_app_phase_complete(self, message: PhaseComplete) -> None:
        self._phase_running = False
        self._current_worker = None
        self.sub_title = message.status
        state = {
            "Completed": "success",
            "Cancelled": "warning",
            "Error": "error",
        }.get(message.status, "idle")
        symbol = {"Completed": "✓", "Cancelled": "!", "Error": "✗"}.get(
            message.status, "●"
        )
        self._set_activity(state, f"{symbol} {message.status}")

    def action_quit(self) -> None:
        if self._phase_running and self._current_worker is not None:
            self._current_worker.cancel()
        self.exit()
