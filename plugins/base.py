"""
Plugin base class for IDE / agent integrations.

To add support for a new editor:
1. Create plugins/<editor_name>.py
2. Subclass DiscoveryPlugin
3. The plugin is auto-discovered by the plugin registry below.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PluginResult:
    """What a plugin returns after scanning its IDE."""
    editor: str
    detected_providers: list[str] = field(default_factory=list)
    installed_agents: list[str] = field(default_factory=list)
    mcp_config_path: Optional[str] = None
    config_path: Optional[str] = None
    extra: dict = field(default_factory=dict)


class DiscoveryPlugin(ABC):
    """
    Base class for environment discovery plugins.

    Each plugin is responsible for one IDE / agent runtime.
    Plugins must be stateless — detect() can be called multiple times.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier: 'cursor', 'claude_code', 'continue', etc."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    def is_present(self) -> bool:
        """
        Fast check — returns True if this IDE/agent appears to be installed.
        Must not make network calls.
        """

    @abstractmethod
    def detect(self) -> Optional[PluginResult]:
        """
        Full detection — reads config files, extracts providers, MCP paths.
        Called only if is_present() returns True.
        Must not make network calls.
        """

    def _home(self) -> Path:
        return Path.home()
