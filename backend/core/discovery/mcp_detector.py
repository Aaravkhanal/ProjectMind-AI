"""
MCP server detector.

Reads config files from Claude Desktop, Cursor, VS Code, Continue.dev
and any project-local .projectmind/mcp.json.
Never makes network calls — pure filesystem reads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .schema import DetectedMCPServer

HOME = Path.home()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def _parse_mcp_servers(raw: dict, source: str) -> list[DetectedMCPServer]:
    """
    Parse the mcpServers dict (Claude Desktop / Cursor / VS Code format):
    {
      "github": {"command": "npx", "args": ["@modelcontextprotocol/server-github"], "env": {...}},
      "postgres": {"command": "npx", "args": [...], "env": {...}}
    }
    """
    servers: list[DetectedMCPServer] = []
    mcp_block = raw.get("mcpServers", raw.get("mcp_servers", raw.get("tools", {})))

    if isinstance(mcp_block, list):
        # Continue.dev uses a list format
        for item in mcp_block:
            name = item.get("name", item.get("id", "unknown"))
            servers.append(DetectedMCPServer(
                name=name,
                command=item.get("command"),
                endpoint=item.get("endpoint") or item.get("url"),
                source=source,
                args=item.get("args", []),
                env={k: "****" for k in item.get("env", {})},
            ))
    elif isinstance(mcp_block, dict):
        for name, cfg in mcp_block.items():
            servers.append(DetectedMCPServer(
                name=name,
                command=cfg.get("command"),
                endpoint=cfg.get("url") or cfg.get("endpoint"),
                source=source,
                args=cfg.get("args", []),
                env={k: "****" for k in cfg.get("env", {})},
            ))

    return servers


# ---------------------------------------------------------------------------
# Per-source readers
# ---------------------------------------------------------------------------

def _claude_desktop() -> list[DetectedMCPServer]:
    candidates = [
        HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        HOME / ".config" / "claude" / "claude_desktop_config.json",
        HOME / ".claude" / "claude_desktop_config.json",
    ]
    for path in candidates:
        if path.exists():
            return _parse_mcp_servers(_read_json(path), "claude_desktop")
    return []


def _cursor() -> list[DetectedMCPServer]:
    candidates = [
        HOME / ".cursor" / "mcp.json",
        HOME / "Library" / "Application Support" / "Cursor" / "User" / "mcp.json",
        HOME / ".config" / "Cursor" / "User" / "mcp.json",
    ]
    for path in candidates:
        if path.exists():
            return _parse_mcp_servers(_read_json(path), "cursor")
    return []


def _vscode_project() -> list[DetectedMCPServer]:
    project_mcp = Path(".vscode") / "mcp.json"
    if project_mcp.exists():
        return _parse_mcp_servers(_read_json(project_mcp), "vscode")
    return []


def _continue_dev() -> list[DetectedMCPServer]:
    candidates = [
        HOME / ".continue" / "config.json",
        HOME / "Library" / "Application Support" / "continue" / "config.json",
        HOME / ".config" / "continue" / "config.json",
    ]
    for path in candidates:
        if path.exists():
            cfg = _read_json(path)
            # Continue uses "mcpServers" or "tools" array
            if cfg.get("mcpServers") or cfg.get("tools"):
                return _parse_mcp_servers(cfg, "continue")
    return []


def _projectmind_local(project_path: Optional[str] = None) -> list[DetectedMCPServer]:
    base = Path(project_path) if project_path else Path(".")
    mcp_file = base / ".projectmind" / "mcp.json"
    if mcp_file.exists():
        return _parse_mcp_servers(_read_json(mcp_file), "projectmind")
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_KNOWN_MCP_SERVERS = {
    "filesystem", "github", "postgres", "mysql", "sqlite",
    "docker", "kubernetes", "browser", "playwright", "puppeteer",
    "slack", "notion", "jira", "linear", "confluence",
    "memory", "fetch", "time", "everything",
}


def detect_all_mcp(project_path: Optional[str] = None) -> list[DetectedMCPServer]:
    """
    Aggregate MCP servers from all known config locations.
    De-duplicates by name (first occurrence wins).
    """
    seen: set[str] = set()
    all_servers: list[DetectedMCPServer] = []

    sources = [
        _claude_desktop,
        _cursor,
        _vscode_project,
        _continue_dev,
        lambda: _projectmind_local(project_path),
    ]

    for source_fn in sources:
        try:
            for srv in source_fn():
                if srv.name not in seen:
                    seen.add(srv.name)
                    all_servers.append(srv)
        except Exception:
            pass

    return all_servers
