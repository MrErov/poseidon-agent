import asyncio

from rich.console import Console
from textual.widgets import ListItem, ListView, RichLog

from poseidon.config_manager import ExecutionConfig
from poseidon.tui import PoseidonApp


def test_tui_starts_with_title_and_phase_list() -> None:
    async def scenario() -> None:
        app = PoseidonApp()
        async with app.run_test():
            assert app.title == "🔱 Poseidon Agent"
            assert app.sub_title == "Ready"
            phase_items = app.query_one(ListView).children
            phase_ids = {child.id for child in phase_items if type(child) is ListItem}
            assert phase_ids == {"phase-0", "phase-1a", "phase-1b", "phase-2", "phase-3", "phase-4"}
            assert app.query_one(RichLog)

    asyncio.run(scenario())


def test_tui_streams_background_phase_output() -> None:
    class FakeRunner:
        def __init__(self, console: Console) -> None:
            self.console = console

        def run(self, **kwargs) -> str:
            self.console.print("Fake streamed response")
            return "Fake streamed response"

    def execution(phase: str) -> ExecutionConfig:
        return ExecutionConfig(
            role="tester",
            executor="api",
            model="nvidia_nim/test-model",
            agent=None,
            herdr={},
        )

    def factory(console: Console, herdr_delegator) -> FakeRunner:
        return FakeRunner(console)

    async def scenario() -> None:
        app = PoseidonApp(
            runner_factory=factory,
            config_resolver=execution,
        )
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "Fake streamed response" in app.output_text
            assert app.sub_title == "Completed"
            assert len(app.query_one(RichLog).lines) > 0

    asyncio.run(scenario())
