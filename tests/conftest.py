import pytest


@pytest.fixture(autouse=True)
def _disable_graphify_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita accesos de red externos salvo que un test configure Graphify."""
    monkeypatch.delenv("GRAPHIFY_MCP_URL", raising=False)
