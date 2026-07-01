"""Cline (claude-dev VS Code extension) discovery plugin."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

class ClinePlugin(DiscoveryPlugin):
    name = "cline"
    display_name = "Cline"

    def _vscode_settings(self) -> Optional[Path]:
        home = self._home()
        for p in [home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
                  home / ".config" / "Code" / "User" / "settings.json"]:
            if p.exists():
                return p
        return None

    def is_present(self) -> bool:
        settings_path = self._vscode_settings()
        if not settings_path:
            return False
        try:
            settings = json.loads(settings_path.read_text(errors="ignore"))
            return "cline" in settings or any("claude-dev" in k for k in settings)
        except Exception:
            return False

    def detect(self) -> Optional[PluginResult]:
        result = PluginResult(editor=self.name, installed_agents=["cline"])
        settings_path = self._vscode_settings()
        if settings_path:
            try:
                settings = json.loads(settings_path.read_text(errors="ignore"))
                cline_cfg = settings.get("cline", settings.get("claude-dev", {}))
                provider = cline_cfg.get("apiProvider", "")
                if provider:
                    result.detected_providers.append(provider.lower())
            except Exception:
                pass
        return result
