"""Windsurf IDE discovery plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

class WindsurfPlugin(DiscoveryPlugin):
    name = "windsurf"
    display_name = "Windsurf"

    def _config_dir(self) -> Optional[Path]:
        home = self._home()
        for d in [home / ".windsurf",
                  home / "Library" / "Application Support" / "Windsurf",
                  home / ".config" / "Windsurf",
                  Path(os.environ.get("APPDATA", "")) / "Windsurf"]:
            if d.exists():
                return d
        return None

    def is_present(self) -> bool:
        return bool(self._config_dir() or os.environ.get("WINDSURF_SESSION"))

    def detect(self) -> Optional[PluginResult]:
        config_dir = self._config_dir()
        result = PluginResult(editor=self.name,
                              config_path=str(config_dir) if config_dir else None,
                              installed_agents=["windsurf"])
        if config_dir:
            try:
                settings = json.loads((config_dir / "User" / "settings.json").read_text(errors="ignore"))
                if settings.get("windsurf", {}).get("apiKey"):
                    result.detected_providers.append("codeium")
            except Exception:
                pass
        return result
