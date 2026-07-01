"""
Plugin registry — auto-discovers all DiscoveryPlugin subclasses
from the plugins/ directory.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.base import DiscoveryPlugin

# Ordered list of plugin module paths to import
_PLUGIN_MODULES = [
    "plugins.cursor",
    "plugins.claude_code",
    "plugins.continue_dev",
    "plugins.cline",
    "plugins.windsurf",
    "plugins.vscode",
    "plugins.local",
    "plugins.custom",
]


def load_all_plugins() -> list["DiscoveryPlugin"]:
    from plugins.base import DiscoveryPlugin as Base
    instances: list[Base] = []

    for mod_path in _PLUGIN_MODULES:
        try:
            mod = importlib.import_module(mod_path)
            for attr in vars(mod).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Base)
                    and attr is not Base
                ):
                    instances.append(attr())
        except Exception:
            pass

    return instances
