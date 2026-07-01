"""VS Code discovery plugin."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from plugins.base import DiscoveryPlugin, PluginResult

_AI_EXTENSIONS = {
    "github.copilot":                  "github-copilot",
    "continue.continue":               "continue",
    "saoudrizwan.claude-dev":          "cline",
    "anthropic.claude":                "claude",
    "codeium.codeium":                 "codeium",
    "tabnine.tabnine-vscode":          "tabnine",
    "amazonwebservices.codewhisperer": "codewhisperer",
}

class VSCodePlugin(DiscoveryPlugin):
    name = "vscode"
    display_name = "VS Code"

    def is_present(self) -> bool:
        home = self._home()
        return any(d.exists() for d in [
            home / ".vscode",
            home / "Library" / "Application Support" / "Code",
            home / ".config" / "Code",
        ]) or os.environ.get("TERM_PROGRAM") == "vscode"

    def detect(self) -> Optional[PluginResult]:
        home = self._home()
        dirs = [home / ".vscode",
                home / "Library" / "Application Support" / "Code",
                home / ".config" / "Code"]
        config_dir = next((d for d in dirs if d.exists()), None)
        result = PluginResult(editor=self.name,
                              config_path=str(config_dir) if config_dir else None)

        ext_dir = home / ".vscode" / "extensions"
        if ext_dir.exists():
            for ext in ext_dir.iterdir():
                name = ext.name.lower()
                for key, label in _AI_EXTENSIONS.items():
                    if key in name and label not in result.installed_agents:
                        result.installed_agents.append(label)

        if os.environ.get("GITHUB_COPILOT_TOKEN") and "github-copilot" not in result.installed_agents:
            result.installed_agents.append("github-copilot")

        project_mcp = Path(".vscode") / "mcp.json"
        if project_mcp.exists():
            result.mcp_config_path = str(project_mcp)

        return result
