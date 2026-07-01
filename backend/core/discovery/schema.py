"""
Environment Discovery schema — all dataclasses are JSON-serializable
so they can be persisted to environment_profile.json.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DetectedModel:
    model_id: str                    # "claude-sonnet-4-6" | "llama3.2" | etc.
    display_name: str
    provider: str                    # "anthropic" | "ollama" | "openai" | etc.
    source: str                      # "env_var" | "ollama" | "lmstudio" | "cursor" | etc.
    is_local: bool = False
    is_free: bool = False
    context_window: Optional[int] = None
    endpoint: Optional[str] = None   # for local/custom models


@dataclass
class DetectedMCPServer:
    name: str
    command: Optional[str] = None    # e.g. "npx @modelcontextprotocol/server-github"
    endpoint: Optional[str] = None   # for HTTP MCP servers
    source: str = "unknown"          # "claude_desktop" | "cursor" | "vscode" | etc.
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class DetectedProvider:
    provider: str                    # "openai" | "anthropic" | etc.
    label: str
    source: str                      # "env_var" | "cursor" | "continue" | etc.
    has_key: bool = True
    key_preview: str = ""            # first 4 chars + "****" for display
    models: list[str] = field(default_factory=list)


@dataclass
class IDEProfile:
    editor: str                      # "cursor" | "vscode" | "claude_code" | etc.
    version: Optional[str] = None
    config_path: Optional[str] = None
    extensions: list[str] = field(default_factory=list)
    detected_providers: list[str] = field(default_factory=list)
    mcp_config_path: Optional[str] = None


@dataclass
class CapabilityMatrix:
    """
    Maps task types → best available model based on discovered environment.
    Built by EnvironmentProfiler after detection.
    """
    # Task → model_id mapping
    best_coding: Optional[str] = None
    best_architecture: Optional[str] = None
    best_security: Optional[str] = None
    best_review: Optional[str] = None
    best_documentation: Optional[str] = None
    best_testing: Optional[str] = None
    best_bug_fix: Optional[str] = None
    best_reasoning: Optional[str] = None
    best_long_context: Optional[str] = None

    # Speed / cost extremes
    cheapest: Optional[str] = None
    fastest: Optional[str] = None
    most_capable: Optional[str] = None

    # Defaults for quick routing
    default_model: Optional[str] = None
    fallback_model: Optional[str] = None


@dataclass
class EnvironmentProfile:
    """
    Complete snapshot of everything detected in the user's environment.
    Persisted to .projectmind/environment_profile.json
    """
    # System
    os_name: str = ""                   # "darwin" | "linux" | "windows"
    os_version: str = ""
    hostname: str = ""
    detected_at: str = ""

    # Primary editor
    editor: str = "unknown"

    # Installed AI agents / extensions
    installed_agents: list[str] = field(default_factory=list)

    # Available providers (with API keys)
    providers: list[DetectedProvider] = field(default_factory=list)

    # All discovered models (cloud + local)
    models: list[DetectedModel] = field(default_factory=list)

    # Local model servers
    local_servers: list[str] = field(default_factory=list)

    # MCP servers
    mcp_servers: list[DetectedMCPServer] = field(default_factory=list)

    # Per-IDE profiles
    ide_profiles: list[IDEProfile] = field(default_factory=list)

    # Computed capability matrix
    capabilities: CapabilityMatrix = field(default_factory=CapabilityMatrix)

    # Raw scan metadata
    scan_duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def provider_names(self) -> list[str]:
        return [p.provider for p in self.providers]

    @property
    def model_ids(self) -> list[str]:
        return [m.model_id for m in self.models]

    @property
    def local_model_ids(self) -> list[str]:
        return [m.model_id for m in self.models if m.is_local]
