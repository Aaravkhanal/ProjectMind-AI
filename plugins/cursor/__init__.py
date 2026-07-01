"""Cursor IDE discovery plugin."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from plugins.base import DiscoveryPlugin, PluginResult


class CursorPlugin(DiscoveryPlugin):
    name = "cursor"
    display_name = "Cursor"

    def _config_dir(self) -> Optional[Path]:
        home = self._home()
        candidates = [
            home / ".cursor",
            home / "Library" / "Application Support" / "Cursor",
            home / ".config" / "Cursor",
            Path(os.environ.get("APPDATA", "")) / "Cursor",
        ]
        return next((d for d in candidates if d.exists()), None)

    def is_present(self) -> bool:
        return bool(self._config_dir() or os.environ.get("CURSOR_SESSION_ID"))

    def detect(self) -> Optional[PluginResult]:
        config_dir = self._config_dir()
        result = PluginResult(editor=self.name, config_path=str(config_dir) if config_dir else None)

        if config_dir:
            for settings_path in [config_dir / "User" / "settings.json", config_dir / "settings.json"]:
                if settings_path.exists():
                    try:
                        settings = json.loads(settings_path.read_text(errors="ignore"))
                        ai = settings.get("cursor", {}).get("aiSettings", {})
                        if ai.get("openaiApiKey"):
                            result.detected_providers.append("openai")
                        if ai.get("anthropicApiKey"):
                            result.detected_providers.append("anthropic")
                        if ai.get("googleAiStudioKey"):
                            result.detected_providers.append("google")
                    except Exception:
                        pass
                    break

            for mcp_path in [config_dir / "mcp.json", config_dir / "User" / "mcp.json"]:
                if mcp_path.exists():
                    result.mcp_config_path = str(mcp_path)
                    break

        return result
