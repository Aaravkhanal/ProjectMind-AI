"""Custom / user-registered model endpoints plugin."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

class CustomPlugin(DiscoveryPlugin):
    name = "custom"
    display_name = "Custom Endpoints"

    def _registry_path(self) -> Path:
        return Path(".projectmind") / "custom_models.json"

    def is_present(self) -> bool:
        return self._registry_path().exists()

    def detect(self) -> Optional[PluginResult]:
        registry_path = self._registry_path()
        if not registry_path.exists():
            return None
        try:
            entries = json.loads(registry_path.read_text(errors="ignore"))
        except Exception:
            return None
        result = PluginResult(editor=self.name)
        for entry in (entries if isinstance(entries, list) else []):
            provider = entry.get("provider", "")
            if provider and provider not in result.detected_providers:
                result.detected_providers.append(provider)
        return result
