"""Continue.dev discovery plugin."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

class ContinuePlugin(DiscoveryPlugin):
    name = "continue"
    display_name = "Continue.dev"

    def _config_dir(self) -> Optional[Path]:
        home = self._home()
        for d in [home / ".continue",
                  home / "Library" / "Application Support" / "continue",
                  home / ".config" / "continue"]:
            if d.exists():
                return d
        return None

    def is_present(self) -> bool:
        return self._config_dir() is not None

    def detect(self) -> Optional[PluginResult]:
        config_dir = self._config_dir()
        if not config_dir:
            return None
        result = PluginResult(editor=self.name,
                              config_path=str(config_dir),
                              installed_agents=["continue"])
        cfg_file = config_dir / "config.json"
        if cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text(errors="ignore"))
                for m in cfg.get("models", []):
                    p = m.get("provider", "").lower()
                    if p and p not in result.detected_providers:
                        result.detected_providers.append(p)
                if cfg.get("mcpServers") or cfg.get("tools"):
                    result.mcp_config_path = str(cfg_file)
            except Exception:
                pass
        return result
