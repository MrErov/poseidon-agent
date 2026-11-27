"""Tests for MCP Registry Manager."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from poseidon.mcp_manager import (
    get_config_paths,
    list_all_mcps,
    read_mcp_config,
    sync_mcp,
    write_mcp_config,
)


def test_get_config_paths_returns_expected_keys() -> None:
    paths = get_config_paths()
    assert "opencode" in paths
    assert "codex" in paths
    assert "claude" in paths
    assert "opencode_alt" in paths


def test_read_mcp_config_opencode(tmp_path: Path) -> None:
    config = {
        "mcp": {
            "servers": {
                "graphify": {
                    "command": "npx",
                    "args": ["-y", "@graphify/mcp-server"],
                    "env": {"API_KEY": "test"},
                }
            }
        }
    }
    config_path = tmp_path / "opencode.json"
    config_path.write_text(json.dumps(config))

    result = read_mcp_config("opencode", config_path)
    assert "graphify" in result
    assert result["graphify"]["command"] == "npx"
    assert result["graphify"]["args"] == ["-y", "@graphify/mcp-server"]
    assert result["graphify"]["env"]["API_KEY"] == "test"


def test_read_mcp_config_codex(tmp_path: Path) -> None:
    config = {
        "mcp_servers": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
            }
        }
    }
    config_path = tmp_path / "config.toml"
    # Write as TOML
    try:
        import tomli_w
        config_path.write_bytes(tomli_w.dumps(config))
    except ImportError:
        # Fallback: write as JSON (tomllib can parse some JSON)
        config_path.write_text(json.dumps(config))

    result = read_mcp_config("codex", config_path)
    assert "github" in result
    assert result["github"]["command"] == "npx"
    assert result["github"]["args"] == ["-y", "@modelcontextprotocol/server-github"]


def test_read_mcp_config_claude(tmp_path: Path) -> None:
    config = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            }
        }
    }
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(config))

    result = read_mcp_config("claude", config_path)
    assert "filesystem" in result
    assert result["filesystem"]["command"] == "npx"


def test_read_mcp_config_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "nonexistent.json"
    result = read_mcp_config("opencode", config_path)
    assert result == {}


def test_read_mcp_config_invalid_json(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{ invalid json")
    result = read_mcp_config("opencode", config_path)
    assert result == {}


def test_list_all_mcps(tmp_path: Path) -> None:
    # Create mock configs
    opencode_config = {
        "mcp": {
            "servers": {
                "graphify": {"command": "npx", "args": ["@graphify/mcp"]}
            }
        }
    }
    codex_config = {
        "mcp_servers": {
            "github": {"command": "npx", "args": ["@mcp/github"]}
        }
    }

    with patch("poseidon.mcp_manager.get_config_paths") as mock_paths:
        mock_paths.return_value = {
            "opencode": tmp_path / "opencode.json",
            "codex": tmp_path / "config.toml",
            "claude": tmp_path / "claude_desktop_config.json",
            "opencode_alt": tmp_path / ".opencode.json",
        }
        (tmp_path / "opencode.json").write_text(json.dumps(opencode_config))
        # Write codex config as TOML
        try:
            import tomli_w
            (tmp_path / "config.toml").write_bytes(tomli_w.dumps(codex_config))
        except ImportError:
            (tmp_path / "config.toml").write_text(json.dumps(codex_config))

        mcps = list_all_mcps()
        assert len(mcps) == 2
        names = {m["name"] for m in mcps}
        assert names == {"graphify", "github"}
        agents = {m["agent"] for m in mcps}
        assert agents == {"opencode", "codex"}


def test_write_mcp_config_opencode(tmp_path: Path) -> None:
    config_path = tmp_path / "opencode.json"
    mcp_servers = {
        "new_server": {"command": "cmd", "args": ["arg1"]}
    }

    write_mcp_config("opencode", config_path, mcp_servers)

    result = json.loads(config_path.read_text())
    assert result["mcp"]["servers"]["new_server"]["command"] == "cmd"


def test_write_mcp_config_preserves_existing(tmp_path: Path) -> None:
    config_path = tmp_path / "opencode.json"
    existing = {"other_setting": "value", "mcp": {"servers": {"existing": {"command": "old"}}}}
    config_path.write_text(json.dumps(existing))

    write_mcp_config("opencode", config_path, {"new": {"command": "new"}})

    result = json.loads(config_path.read_text())
    assert result["other_setting"] == "value"
    assert "existing" in result["mcp"]["servers"]
    assert "new" in result["mcp"]["servers"]
    assert result["mcp"]["servers"]["new"]["command"] == "new"


def test_sync_mcp_success(tmp_path: Path) -> None:
    source_config = {
        "mcp": {
            "servers": {
                "graphify": {"command": "npx", "args": ["@graphify/mcp"]}
            }
        }
    }

    with patch("poseidon.mcp_manager.get_config_paths") as mock_paths:
        mock_paths.return_value = {
            "opencode": tmp_path / "opencode.json",
            "codex": tmp_path / "config.toml",
            "claude": tmp_path / "claude_desktop_config.json",
            "opencode_alt": tmp_path / ".opencode.json",
        }
        (tmp_path / "opencode.json").write_text(json.dumps(source_config))
        (tmp_path / "config.toml").write_text(json.dumps({"mcp_servers": {}}))

        success = sync_mcp("graphify", "opencode", "codex")
        assert success

        # Verify target was updated
        target_data = json.loads((tmp_path / "config.toml").read_text())
        assert "graphify" in target_data["mcp_servers"]
        assert target_data["mcp_servers"]["graphify"]["command"] == "npx"


def test_sync_mcp_not_found(tmp_path: Path) -> None:
    source_config = {"mcp": {"servers": {}}}
    target_config = {"mcp_servers": {}}

    with patch("poseidon.mcp_manager.get_config_paths") as mock_paths:
        mock_paths.return_value = {
            "opencode": tmp_path / "opencode.json",
            "codex": tmp_path / "config.toml",
            "claude": tmp_path / "claude_desktop_config.json",
            "opencode_alt": tmp_path / ".opencode.json",
        }
        (tmp_path / "opencode.json").write_text(json.dumps(source_config))
        (tmp_path / "config.toml").write_text(json.dumps(target_config))

        success = sync_mcp("nonexistent", "opencode", "codex")
        assert not success


def test_sync_mcp_invalid_agent() -> None:
    with pytest.raises(ValueError):
        sync_mcp("test", "invalid", "codex")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])