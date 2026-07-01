"""
IDE / editor detector.

Pure filesystem + environment inspection — no subprocesses, no network.
Each detector returns an IDEProfile if the IDE is found, else None.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .schema import IDEProfile

HOME = Path.home()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def _json_paths(*candidates: Path) -> Optional[Path]:
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------

def detect_cursor() -> Optional[IDEProfile]:
    cursor_dirs = [
        HOME / ".cursor",
        HOME / "Library" / "Application Support" / "Cursor",
        HOME / ".config" / "Cursor",
        Path(os.environ.get("APPDATA", "")) / "Cursor",
    ]
    config_dir = next((d for d in cursor_dirs if d.exists()), None)
    if not config_dir and not os.environ.get("CURSOR_SESSION_ID"):
        return None

    profile = IDEProfile(
        editor="cursor",
        config_path=str(config_dir) if config_dir else None,
    )

    if config_dir:
        settings_path = _json_paths(
            config_dir / "User" / "settings.json",
            config_dir / "settings.json",
        )
        if settings_path:
            settings = _read_json(settings_path)
            cursor_ai = settings.get("cursor", {}).get("aiSettings", {})
            if cursor_ai.get("openaiApiKey"):
                profile.detected_providers.append("openai")
            if cursor_ai.get("anthropicApiKey"):
                profile.detected_providers.append("anthropic")
            if cursor_ai.get("googleAiStudioKey"):
                profile.detected_providers.append("google")

        mcp_path = _json_paths(
            config_dir / "mcp.json",
            config_dir / "User" / "mcp.json",
        )
        if mcp_path:
            profile.mcp_config_path = str(mcp_path)

    return profile


# ---------------------------------------------------------------------------
# VS Code
# ---------------------------------------------------------------------------

def detect_vscode() -> Optional[IDEProfile]:
    vscode_dirs = [
        HOME / ".vscode",
        HOME / "Library" / "Application Support" / "Code",
        HOME / ".config" / "Code",
        Path(os.environ.get("APPDATA", "")) / "Code",
    ]
    config_dir = next((d for d in vscode_dirs if d.exists()), None)
    if not config_dir and os.environ.get("TERM_PROGRAM") != "vscode":
        return None

    profile = IDEProfile(
        editor="vscode",
        config_path=str(config_dir) if config_dir else None,
    )

    _AI_EXTENSIONS = {
        "github.copilot":                    "github-copilot",
        "continue.continue":                 "continue",
        "saoudrizwan.claude-dev":            "cline",
        "anthropic.claude":                  "claude",
        "codeium.codeium":                   "codeium",
        "tabnine.tabnine-vscode":            "tabnine",
        "amazonwebservices.codewhisperer":   "codewhisperer",
    }

    extensions_dir = (HOME / ".vscode" / "extensions")
    if extensions_dir.exists():
        for ext_dir in extensions_dir.iterdir():
            name = ext_dir.name.lower()
            for key, label in _AI_EXTENSIONS.items():
                if key in name and label not in profile.extensions:
                    profile.extensions.append(label)

    project_mcp = Path(".vscode") / "mcp.json"
    if project_mcp.exists():
        profile.mcp_config_path = str(project_mcp)

    return profile


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

def detect_claude_code() -> Optional[IDEProfile]:
    claude_dirs = [
        HOME / ".claude",
        HOME / "Library" / "Application Support" / "Claude",
        HOME / ".config" / "claude",
    ]
    config_dir = next((d for d in claude_dirs if d.exists()), None)

    env_markers = ["CLAUDE_CODE", "CLAUDE_SESSION_ID", "CLAUDE_API_KEY", "CLAUDE_CODE_SESSION"]
    running_in_claude = any(os.environ.get(m) for m in env_markers)

    if not config_dir and not running_in_claude:
        return None

    profile = IDEProfile(
        editor="claude_code",
        config_path=str(config_dir) if config_dir else None,
    )
    profile.detected_providers.append("anthropic")

    mcp_path = _json_paths(
        HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        HOME / ".config" / "claude" / "claude_desktop_config.json",
        HOME / ".claude" / "claude_desktop_config.json",
    )
    if mcp_path:
        profile.mcp_config_path = str(mcp_path)

    return profile


# ---------------------------------------------------------------------------
# Continue.dev
# ---------------------------------------------------------------------------

def detect_continue() -> Optional[IDEProfile]:
    continue_dirs = [
        HOME / ".continue",
        HOME / "Library" / "Application Support" / "continue",
        HOME / ".config" / "continue",
    ]
    config_dir = next((d for d in continue_dirs if d.exists()), None)
    if not config_dir:
        return None

    profile = IDEProfile(editor="continue", config_path=str(config_dir))

    config_file = _json_paths(config_dir / "config.json")
    if config_file:
        cfg = _read_json(config_file)
        for model_cfg in cfg.get("models", []):
            provider = model_cfg.get("provider", "").lower()
            if provider and provider not in profile.detected_providers:
                profile.detected_providers.append(provider)
        if cfg.get("mcpServers") or cfg.get("tools"):
            profile.mcp_config_path = str(config_file)

    return profile


# ---------------------------------------------------------------------------
# Cline
# ---------------------------------------------------------------------------

def detect_cline() -> Optional[IDEProfile]:
    vscode_settings_path = _json_paths(
        HOME / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        HOME / ".config" / "Code" / "User" / "settings.json",
    )
    has_cline = False
    if vscode_settings_path:
        settings = _read_json(vscode_settings_path)
        if "cline" in settings or any("claude-dev" in k for k in settings):
            has_cline = True

    cline_dir = HOME / ".cline"
    if not cline_dir.exists() and not has_cline:
        return None

    profile = IDEProfile(
        editor="cline",
        config_path=str(cline_dir) if cline_dir.exists() else None,
    )

    if vscode_settings_path and has_cline:
        settings = _read_json(vscode_settings_path)
        cline_cfg = settings.get("cline", settings.get("claude-dev", {}))
        provider = cline_cfg.get("apiProvider", "")
        if provider:
            profile.detected_providers.append(provider.lower())

    return profile


# ---------------------------------------------------------------------------
# Windsurf
# ---------------------------------------------------------------------------

def detect_windsurf() -> Optional[IDEProfile]:
    windsurf_dirs = [
        HOME / ".windsurf",
        HOME / "Library" / "Application Support" / "Windsurf",
        HOME / ".config" / "Windsurf",
        Path(os.environ.get("APPDATA", "")) / "Windsurf",
    ]
    config_dir = next((d for d in windsurf_dirs if d.exists()), None)
    if not config_dir and not os.environ.get("WINDSURF_SESSION"):
        return None

    profile = IDEProfile(
        editor="windsurf",
        config_path=str(config_dir) if config_dir else None,
    )
    if config_dir:
        settings = _read_json(config_dir / "User" / "settings.json")
        if settings.get("windsurf", {}).get("apiKey"):
            profile.detected_providers.append("codeium")

    return profile


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DETECTORS = [
    detect_cursor,
    detect_vscode,
    detect_claude_code,
    detect_continue,
    detect_cline,
    detect_windsurf,
]

_PRIORITY = ["claude_code", "cursor", "windsurf", "vscode", "continue", "cline"]


def detect_all_ides() -> tuple[list[IDEProfile], str]:
    """
    Run all IDE detectors.
    Returns (profiles, primary_editor).
    """
    profiles: list[IDEProfile] = []
    for detector in _DETECTORS:
        try:
            result = detector()
            if result:
                profiles.append(result)
        except Exception:
            pass

    found_editors = {p.editor for p in profiles}
    primary = next((e for e in _PRIORITY if e in found_editors), "unknown")

    # Active-session env vars take priority
    if os.environ.get("CURSOR_SESSION_ID"):
        primary = "cursor"
    elif any(os.environ.get(m) for m in ["CLAUDE_CODE", "CLAUDE_SESSION_ID"]):
        primary = "claude_code"
    elif os.environ.get("WINDSURF_SESSION"):
        primary = "windsurf"
    elif os.environ.get("TERM_PROGRAM") == "vscode":
        primary = "vscode"

    return profiles, primary
