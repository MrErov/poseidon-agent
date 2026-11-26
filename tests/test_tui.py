import asyncio
import threading
from pathlib import Path

import pytest
from rich.console import Console
from textual.widgets import (
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RichLog,
    Select,
)

from poseidon.config_manager import ExecutionConfig
from poseidon.tui import PoseidonApp


def _execution(phase: str) -> ExecutionConfig:
    return ExecutionConfig(
        role="tester",
        executor="api",
        model="nvidia_nim/test-model",
        agent=None,
        herdr={},
    )


def test_tui_starts_with_title_and_phase_list() -> None:
    async def scenario() -> None:
        app = PoseidonApp()
        async with app.run_test():
            assert app.title == "🔱 Poseidon Agent"
            assert app.sub_title == "Ready"
            phase_items = app.query_one(ListView).children
            phase_ids = {child.id for child in phase_items if type(child) is ListItem}
            assert phase_ids == {
                "phase-0",
                "phase-1a",
                "phase-1b",
                "phase-2",
                "phase-3",
                "phase-4",
            }
            assert app.query_one(RichLog)

    asyncio.run(scenario())


def test_tui_streams_background_phase_output() -> None:
    class FakeRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            self.console.print("Fake streamed response")
            return "Fake streamed response"

    def factory(console: Console, herdr_delegator) -> FakeRunner:
        return FakeRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(
            runner_factory=factory,
            config_resolver=_execution,
        )
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "Fake streamed response" in app.output_text
            assert app.sub_title == "Completed"
            assert len(app.query_one(RichLog).lines) > 0

    asyncio.run(scenario())


def test_tui_wide_layout_keeps_sidebar_and_hides_selector() -> None:
    async def scenario() -> None:
        app = PoseidonApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            assert not app.screen.has_class("narrow")
            assert not app.screen.has_class("tiny")
            assert app.query_one("#sidebar").display is True
            assert app.query_one("#phase-select-row").display is False
            assert app.query_one("#too-small").display is False

    asyncio.run(scenario())


def test_tui_narrow_layout_replaces_sidebar_with_phase_selector() -> None:
    async def scenario() -> None:
        app = PoseidonApp()
        async with app.run_test(size=(60, 24)) as pilot:
            await pilot.pause()
            assert app.screen.has_class("narrow")
            assert not app.screen.has_class("tiny")
            assert app.query_one("#sidebar").display is False
            assert app.query_one("#phase-select-row").display is True

            select = app.query_one("#phase-select", Select)
            select.value = "1b"
            await pilot.pause()
            assert app.selected_phase == "1b"
            assert app.sub_title == "Selected 1b"

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(36, 24), (120, 10)])
def test_tui_tiny_layout_shows_minimum_size_notice(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app = PoseidonApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.screen.has_class("tiny")
            assert app.query_one("#main").display is False
            assert app.query_one("#too-small").display is True

    asyncio.run(scenario())


def test_tui_shows_spinner_and_completion_feedback() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            self.console.print("Working...")
            started.set()
            release.wait(timeout=5)
            return "done"

    def factory(console: Console, herdr_delegator) -> BlockingRunner:
        return BlockingRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(runner_factory=factory, config_resolver=_execution)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("ctrl+r")
            for _ in range(200):
                if started.is_set():
                    break
                await pilot.pause()
                await asyncio.sleep(0.01)
            assert started.is_set()

            spinner = app.query_one("#spinner", LoadingIndicator)
            label = app.query_one("#activity-label", Label)
            assert spinner.display is True
            assert "Running phase 0" in str(label.content)

            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert spinner.display is False
            assert "Completed" in str(label.content)
            assert app.sub_title == "Completed"

    asyncio.run(scenario())


def test_tui_cancel_shows_warning_feedback() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            started.set()
            release.wait(timeout=5)
            return "done"

    def factory(console: Console, herdr_delegator) -> BlockingRunner:
        return BlockingRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(runner_factory=factory, config_resolver=_execution)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("ctrl+r")
            for _ in range(200):
                if started.is_set():
                    break
                await pilot.pause()
                await asyncio.sleep(0.01)
            assert started.is_set()

            await pilot.press("ctrl+x")
            await pilot.pause()

            assert app.query_one("#spinner", LoadingIndicator).display is False
            assert "Cancelled" in str(app.query_one("#activity-label", Label).content)
            assert app.sub_title == "Cancelled"

            release.set()
            await app.workers.wait_for_complete()

    asyncio.run(scenario())


def test_tui_error_shows_error_feedback() -> None:
    class FailingRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            raise RuntimeError("boom")

    def factory(console: Console, herdr_delegator) -> FailingRunner:
        return FailingRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(runner_factory=factory, config_resolver=_execution)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("ctrl+r")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.query_one("#spinner", LoadingIndicator).display is False
            assert "Error" in str(app.query_one("#activity-label", Label).content)
            assert "boom" in app.output_text

    asyncio.run(scenario())


def test_get_working_dir_returns_executable_parent_when_frozen(monkeypatch) -> None:
    """Test that get_working_dir returns the executable parent when frozen."""
    # Simulate frozen state by directly testing the function logic
    import poseidon.utils as utils_module

    # Test the logic directly since we can't easily monkeypatch sys.frozen
    # In frozen state: getattr(sys, 'frozen', False) returns True
    # So we test the function with a mock sys module
    class MockSys:
        frozen = True
        executable = "/fake/dir/poseidon.exe"

    original_sys = utils_module.sys
    utils_module.sys = MockSys
    try:
        assert utils_module.get_working_dir() == Path("/fake/dir")
    finally:
        utils_module.sys = original_sys


def test_tui_cancel_calls_herdr_kill(monkeypatch) -> None:
    """Test that cancelling a phase with Herdr calls kill_terminal."""
    started = threading.Event()
    release = threading.Event()
    kill_called = threading.Event()

    class BlockingRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            # Simulate herdr execution with cancel_event checking
            cancel_event = kwargs.get("cancel_event")
            self.console.print("Working...")
            started.set()
            # Wait for either release or cancel
            while not release.is_set():
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Cancelled")
                release.wait(timeout=0.1)
            return "done"

    class FakeHerdr:
        def __init__(self) -> None:
            self.last_terminal_address = "t123"
            self.kill_called = False

        def kill_terminal(self, address: str) -> None:
            assert address == "t123"
            self.kill_called = True
            kill_called.set()

    def factory(console: Console, herdr_delegator) -> BlockingRunner:
        return BlockingRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(runner_factory=factory, config_resolver=_execution)
        # Inject fake herdr
        app._last_herdr = FakeHerdr()

        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("ctrl+r")
            for _ in range(200):
                if started.is_set():
                    break
                await pilot.pause()
                await asyncio.sleep(0.01)
            assert started.is_set()

            await pilot.press("ctrl+x")
            await pilot.pause()

            # Verify kill was called
            assert kill_called.is_set(), "kill_terminal was not called on cancel"
            assert app._last_herdr.kill_called

            release.set()
            await app.workers.wait_for_complete()

    asyncio.run(scenario())
