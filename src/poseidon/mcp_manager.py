"""MCP Registry Manager for Poseidon.

Manages MCP (Model Context Protocol) configurations across different AI agents
like OpenCode, Codex, Claude Code, etc.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import tomllib


def get_config_paths() -> dict[str, Path]:
    """Return known MCP config file paths for supported agents."""
    home = Path.home()
    paths = {}

    # OpenCode
    if sys.platform == "win32":
        opencode_dir = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "opencode"
    else:
        opencode_dir = home / ".config" / "opencode"
    paths["opencode"] = opencode_dir / "opencode.json"

    # Codex
    if sys.platform == "win32":
        codex_dir = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "codex"
    else:
        codex_dir = home / ".codex"
    paths["codex"] = codex_dir / "config.toml"

    # Claude Code
    if sys.platform == "win32":
        claude_dir = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "claude"
    else:
        claude_dir = home / ".claude"
    paths["claude"] = claude_dir / "claude_desktop_config.json"

    # OpenCode (alternative location)
    paths["opencode_alt"] = home / ".opencode.json"

    return paths


def read_mcp_config(agent: str, config_path: Path) -> dict[str, Any]:
    """Read MCP configuration from an agent's config file."""
    if not config_path.is_file():
        return {}

    try:
        if agent == "codex" and config_path.suffix == ".toml":
            with config_path.open("rb") as f:
                try:
                    data = tomllib.load(f)
                except tomllib.TOMLDecodeError:
                    # Fallback: try to parse as JSON (some users may have JSON in .toml files)
                    with config_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
        else:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, OSError):
        return {}

    # Extract MCP servers based on agent config structure
    mcp_servers = {}

    if agent == "opencode":
        # OpenCode: { "mcp": { "servers": { "name": { "command": "...", "args": [...] } } } }
        mcp_data = data.get("mcp", {})
        servers = mcp_data.get("servers", {})
        for name, config in servers.items():
            mcp_servers[name] = {
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "env": config.get("env", {}),
                "disabled": config.get("disabled", False),
            }
    elif agent == "codex":
        # Codex: { "mcp_servers": { "name": { "command": "...", "args": [...] } } }
        servers = data.get("mcp_servers", {})
        for name, config in servers.items():
            mcp_servers[name] = {
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "env": config.get("env", {}),
            }
    elif agent == "claude":
        # Claude: { "mcpServers": { "name": { "command": "...", "args": [...], "env": {...} } } }
        servers = data.get("mcpServers", {})
        for name, config in servers.items():
            mcp_servers[name] = {
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "env": config.get("env", {}),
            }

    return mcp_servers


def list_all_mcps() -> list[dict[str, Any]]:
    """List all MCP servers across all known agents."""
    config_paths = get_config_paths()
    all_mcps = []

    for agent, config_path in config_paths.items():
        # Skip alternative paths if main already found
        if agent == "opencode_alt" and config_paths["opencode"].is_file():
            continue

        mcp_servers = read_mcp_config(agent.replace("_alt", ""), config_path)
        for name, config in mcp_servers.items():
            all_mcps.append({
                "name": name,
                "agent": agent.replace("_alt", ""),
                "config_path": str(config_path),
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "env": config.get("env", {}),
                "disabled": config.get("disabled", False),
            })

    return all_mcps


def get_agent_config_structure(agent: str) -> dict[str, Any]:
    """Get the expected config structure for an agent."""
    if agent == "opencode":
        return {"mcp": {"servers": {}}}
    elif agent == "codex":
        return {"mcp_servers": {}}
    elif agent == "claude":
        return {"mcpServers": {}}
    return {}


def write_mcp_config(agent: str, config_path: Path, mcp_servers: dict[str, Any]) -> None:
    """Write MCP servers to an agent's config file, merging with existing servers."""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config to preserve other settings
    existing = {}
    if config_path.is_file():
        try:
            if agent == "codex" and config_path.suffix == ".toml":
                with config_path.open("rb") as f:
                    existing = tomllib.load(f)
            else:
                with config_path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError, OSError):
            existing = {}

    # Update MCP servers (merge with existing)
    if agent == "opencode":
        if "mcp" not in existing:
            existing["mcp"] = {}
        if "servers" not in existing["mcp"]:
            existing["mcp"]["servers"] = {}
        existing["mcp"]["servers"].update(mcp_servers)
    elif agent == "codex":
        if "mcp_servers" not in existing:
            existing["mcp_servers"] = {}
        existing["mcp_servers"].update(mcp_servers)
    elif agent == "claude":
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        existing["mcpServers"].update(mcp_servers)

    # Write back
    try:
        if agent == "codex":
            # Try to use tomli_w for TOML, fallback to JSON
            try:
                import tomli_w
                with config_path.open("wb") as f:
                    tomli_w.dump(existing, f)
            except ImportError:
                # Fallback: write as JSON with .toml extension
                with config_path.open("w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2)
        else:
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
    except OSError as exc:
        raise RuntimeError(f"Could not write config to {config_path}: {exc}") from exc


def sync_mcp(
    mcp_name: str,
    source_agent: str,
    target_agent: str,
    config_paths: dict[str, Path] | None = None,
) -> bool:
    """Sync an MCP server from one agent to another.

    Returns True if successful, False if source MCP not found.
    """
    if config_paths is None:
        config_paths = get_config_paths()

    source_path = config_paths.get(source_agent)
    target_path = config_paths.get(target_agent)

    if not source_path or not target_path:
        raise ValueError(f"Unknown agent: {source_agent} or {target_agent}")

    # Read source MCP
    source_mcps = read_mcp_config(source_agent, source_path)
    if mcp_name not in source_mcps:
        return False

    mcp_config = source_mcps[mcp_name]

    # Read target config
    target_mcps = read_mcp_config(target_agent, target_path)

    # Add/update MCP in target
    target_mcps[mcp_name] = mcp_config

    # Write back
    write_mcp_config(target_agent, target_path, target_mcps)

    return True


def format_mcp_table(mcps: list[dict[str, Any]]) -> str:
    """Format MCP list as a Rich table string."""
    from rich.table import Table

    table = Table(title="📡 MCP Registry", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Command", style="green")
    table.add_column("Args", style="yellow")
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

    return table


if __name__ == "__main__":
    # Quick test
    mcps = list_all_mcps()
    print(format_mcp_table(mcps))