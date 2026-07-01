"""Local model server discovery plugin (Ollama, LM Studio, vLLM, llama.cpp)."""
from __future__ import annotations
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

class LocalModelsPlugin(DiscoveryPlugin):
    name = "local"
    display_name = "Local Models"

    def is_present(self) -> bool:
        # Actual detection happens via HTTP in local_detector.py;
        # this plugin always runs to trigger that check.
        return True

    def detect(self) -> Optional[PluginResult]:
        # Runtime detection is handled by local_detector.py.
        # This plugin signals that local model detection should run.
        return PluginResult(editor=self.name, extra={"run_local_scan": True})
