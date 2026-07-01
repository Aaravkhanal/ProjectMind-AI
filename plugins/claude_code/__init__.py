"""Claude Code discovery plugin."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

_ENV_MARKERS = ["CLAUDE_CODE", "CLAUDE_SESSION_ID", "CLAUDE_API_KEY", "CLAUDE_CODE_SESSION"]

class ClaudeCodePlugin(DiscoveryPlugin):
    name = "claude_code"
    display_name = "Claude Code"

    def is_present(self) -> bool:
        dirs = [self._home() / ".claude",
                self._home() / "Library" / "Application Support" / "Claude",
                self._home() / ".config" / "claude"]
        return any(os.environ.get(m) for m in _ENV_MARKERS) or any(d.exists() for d in dirs)

    def detect(self) -> Optional[PluginResult]:
        home = self._home()
        dirs = [home / ".claude",
                home / "Library" / "Application Support" / "Claude",
                home / ".config" / "claude"]
        config_dir = next((d for d in dirs if d.exists()), None)
        result = PluginResult(editor=self.name,
                              config_path=str(config_dir) if config_dir else None,
                              detected_providers=["anthropic"],
                              installed_agents=["claude-code"])
        for p in [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                  home / ".config" / "claude" / "claude_desktop_config.json",
                  home / ".claude" / "claude_desktop_config.json"]:
            if p.exists():
                result.mcp_config_path = str(p)
                break
        return result
