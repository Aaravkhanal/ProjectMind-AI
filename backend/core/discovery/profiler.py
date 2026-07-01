"""
Environment Profiler — the main orchestrator.

Calls all sub-detectors, assembles EnvironmentProfile,
computes CapabilityMatrix, and persists to .projectmind/environment_profile.json.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .ide_detector import detect_all_ides
from .local_detector import detect_all_local
from .mcp_detector import detect_all_mcp
from .os_detector import detect_env_providers, detect_os
from .schema import CapabilityMatrix, DetectedModel, EnvironmentProfile


# ---------------------------------------------------------------------------
# Capability scoring — determines which model is "best" for each task.
# Higher score = better fit.  These are heuristic tier rankings; the
# ModelProfiler (backend/core/providers/profiler.py) can override them
# with actual benchmark scores once a key is confirmed.
# ---------------------------------------------------------------------------

# provider → task → score (0–10)
_PROVIDER_SCORES: dict[str, dict[str, float]] = {
    "anthropic": {
        "coding": 9.5, "architecture": 9.5, "security": 9.0,
        "review": 9.5, "documentation": 9.0, "testing": 9.0,
        "bug_fix": 9.5, "reasoning": 9.5, "long_context": 9.5,
        "speed": 7.0, "cost": 5.0,
    },
    "openai": {
        "coding": 9.0, "architecture": 9.0, "security": 8.5,
        "review": 9.0, "documentation": 8.5, "testing": 8.5,
        "bug_fix": 9.0, "reasoning": 9.0, "long_context": 8.5,
        "speed": 7.5, "cost": 5.5,
    },
    "google": {
        "coding": 8.5, "architecture": 8.5, "security": 8.0,
        "review": 8.5, "documentation": 8.5, "testing": 8.0,
        "bug_fix": 8.0, "reasoning": 8.5, "long_context": 9.5,
        "speed": 8.0, "cost": 8.0,
    },
    "deepseek": {
        "coding": 9.0, "architecture": 8.0, "security": 7.5,
        "review": 8.5, "documentation": 7.5, "testing": 8.5,
        "bug_fix": 9.0, "reasoning": 8.5, "long_context": 7.0,
        "speed": 7.5, "cost": 9.5,
    },
    "groq": {
        "coding": 7.5, "architecture": 7.0, "security": 7.0,
        "review": 7.5, "documentation": 7.0, "testing": 7.5,
        "bug_fix": 7.5, "reasoning": 7.0, "long_context": 6.0,
        "speed": 9.5, "cost": 8.5,
    },
    "mistral": {
        "coding": 8.5, "architecture": 8.0, "security": 7.5,
        "review": 8.0, "documentation": 8.0, "testing": 8.0,
        "bug_fix": 8.0, "reasoning": 7.5, "long_context": 8.0,
        "speed": 8.0, "cost": 8.5,
    },
    "xai": {
        "coding": 8.5, "architecture": 8.5, "security": 8.0,
        "review": 8.5, "documentation": 8.0, "testing": 8.0,
        "bug_fix": 8.5, "reasoning": 9.0, "long_context": 8.0,
        "speed": 7.5, "cost": 6.0,
    },
    "openrouter": {
        "coding": 8.0, "architecture": 8.0, "security": 7.5,
        "review": 8.0, "documentation": 7.5, "testing": 7.5,
        "bug_fix": 8.0, "reasoning": 8.0, "long_context": 8.0,
        "speed": 7.0, "cost": 8.0,
    },
    "ollama": {
        "coding": 7.0, "architecture": 6.5, "security": 6.0,
        "review": 6.5, "documentation": 6.5, "testing": 7.0,
        "bug_fix": 7.0, "reasoning": 6.5, "long_context": 5.5,
        "speed": 6.0, "cost": 10.0,
    },
    "lmstudio": {
        "coding": 6.5, "architecture": 6.0, "security": 5.5,
        "review": 6.0, "documentation": 6.0, "testing": 6.5,
        "bug_fix": 6.5, "reasoning": 6.0, "long_context": 5.0,
        "speed": 5.5, "cost": 10.0,
    },
}

# Best model per provider (used when we pick the representative model)
_BEST_MODEL: dict[str, str] = {
    "anthropic":  "claude-sonnet-4-6",
    "openai":     "gpt-4o",
    "google":     "gemini/gemini-2.5-pro",
    "deepseek":   "deepseek/deepseek-chat",
    "groq":       "groq/llama-3.3-70b-versatile",
    "mistral":    "mistral/mistral-large-latest",
    "xai":        "xai/grok-3",
    "openrouter": "openrouter/auto",
}


def _best_model_for(
    task: str,
    available_providers: list[str],
    all_models: list[DetectedModel],
) -> Optional[str]:
    best_score = -1.0
    best_model: Optional[str] = None

    for provider in available_providers:
        score = _PROVIDER_SCORES.get(provider, {}).get(task, 0.0)
        if score > best_score:
            best_score = score
            preferred = _BEST_MODEL.get(provider)
            if preferred and any(m.model_id == preferred for m in all_models):
                # Model was explicitly discovered (env var key or local probe)
                best_model = preferred
            elif preferred:
                # Provider is known (detected via IDE plugin) — trust the catalog
                best_model = preferred
            else:
                # Local model with no catalog entry — pick first discovered
                candidates = [m.model_id for m in all_models if m.provider == provider]
                if candidates:
                    best_model = candidates[0]

    return best_model


def _build_capability_matrix(
    providers: list[str],
    models: list[DetectedModel],
) -> CapabilityMatrix:
    def best(task: str) -> Optional[str]:
        return _best_model_for(task, providers, models)

    # Speed champion — Groq if available, else fastest available
    speed_order = ["groq", "mistral", "openai", "google", "anthropic"]
    fastest = next(
        (_BEST_MODEL.get(p) or next((m.model_id for m in models if m.provider == p), None)
         for p in speed_order if p in providers),
        None,
    )

    # Cost champion — local first, then deepseek, then groq
    cost_order = ["ollama", "lmstudio", "llamacpp", "vllm", "deepseek", "groq", "mistral"]
    cheapest = next(
        (next((m.model_id for m in models if m.provider == p), None)
         for p in cost_order if p in providers),
        None,
    )

    # Power champion — claude > openai > google > xai
    power_order = ["anthropic", "openai", "xai", "google", "deepseek"]
    most_capable = next(
        (_BEST_MODEL.get(p) or next((m.model_id for m in models if m.provider == p), None)
         for p in power_order if p in providers),
        None,
    )

    default = most_capable or fastest or cheapest
    fallback = cheapest if cheapest != default else fastest

    return CapabilityMatrix(
        best_coding=best("coding"),
        best_architecture=best("architecture"),
        best_security=best("security"),
        best_review=best("review"),
        best_documentation=best("documentation"),
        best_testing=best("testing"),
        best_bug_fix=best("bug_fix"),
        best_reasoning=best("reasoning"),
        best_long_context=best("long_context"),
        fastest=fastest,
        cheapest=cheapest,
        most_capable=most_capable,
        default_model=default,
        fallback_model=fallback,
    )


# ---------------------------------------------------------------------------
# Main profiler
# ---------------------------------------------------------------------------

class EnvironmentProfiler:
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)

    def scan(self) -> EnvironmentProfile:
        t0 = time.monotonic()
        profile = EnvironmentProfile(
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        errors: list[str] = []

        # 1. OS
        try:
            os_info = detect_os()
            profile.os_name = os_info["os_name"]
            profile.os_version = os_info["os_version"]
            profile.hostname = os_info["hostname"]
        except Exception as e:
            errors.append(f"os_detect: {e}")

        # 2. Environment variables → providers + cloud models
        try:
            env_providers, env_models = detect_env_providers()
            profile.providers.extend(env_providers)
            profile.models.extend(env_models)
        except Exception as e:
            errors.append(f"env_providers: {e}")

        # 3. IDE detection
        try:
            ide_profiles, primary = detect_all_ides()
            profile.ide_profiles = ide_profiles
            profile.editor = primary

            # Collect agents from IDE profiles
            for ide in ide_profiles:
                profile.installed_agents.extend(ide.extensions)
        except Exception as e:
            errors.append(f"ide_detect: {e}")

        # 4. Local model servers (Ollama, LM Studio, vLLM, llama.cpp)
        try:
            local_models, local_providers, active_servers = detect_all_local()
            profile.models.extend(local_models)
            profile.providers.extend(local_providers)
            profile.local_servers = active_servers
        except Exception as e:
            errors.append(f"local_detect: {e}")

        # 5. MCP servers
        try:
            profile.mcp_servers = detect_all_mcp(str(self.project_path))
        except Exception as e:
            errors.append(f"mcp_detect: {e}")

        # 6. Plugin registry (extends above with plugin-specific info)
        try:
            self._run_plugins(profile)
        except Exception as e:
            errors.append(f"plugins: {e}")

        # 7. Build capability matrix from what we found
        try:
            all_provider_names = list({p.provider for p in profile.providers})
            profile.capabilities = _build_capability_matrix(all_provider_names, profile.models)
        except Exception as e:
            errors.append(f"capability_matrix: {e}")

        profile.scan_duration_ms = (time.monotonic() - t0) * 1000
        profile.errors = errors

        # Persist
        self._save(profile)
        return profile

    def _run_plugins(self, profile: EnvironmentProfile) -> None:
        try:
            from plugins import load_all_plugins
            for plugin in load_all_plugins():
                if not plugin.is_present():
                    continue
                result = plugin.detect()
                if not result:
                    continue
                for agent in result.installed_agents:
                    if agent not in profile.installed_agents:
                        profile.installed_agents.append(agent)
                for prov in result.detected_providers:
                    existing = {p.provider for p in profile.providers}
                    if prov not in existing:
                        from .schema import DetectedProvider
                        profile.providers.append(DetectedProvider(
                            provider=prov,
                            label=prov.title(),
                            source=f"plugin:{plugin.name}",
                        ))
        except Exception:
            pass

    def _save(self, profile: EnvironmentProfile) -> None:
        out_dir = self.project_path / ".projectmind"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "environment_profile.json"
        try:
            out_file.write_text(
                json.dumps(profile.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    def load_cached(self) -> Optional[EnvironmentProfile]:
        cached = self.project_path / ".projectmind" / "environment_profile.json"
        if not cached.exists():
            return None
        try:
            from dataclasses import fields
            from .schema import (CapabilityMatrix, DetectedMCPServer,
                                 DetectedModel, DetectedProvider, IDEProfile)
            raw = json.loads(cached.read_text())

            providers = [DetectedProvider(**p) for p in raw.get("providers", [])]
            models = [DetectedModel(**m) for m in raw.get("models", [])]
            mcp_servers = [DetectedMCPServer(**s) for s in raw.get("mcp_servers", [])]
            ide_profiles = [IDEProfile(**i) for i in raw.get("ide_profiles", [])]
            capabilities = CapabilityMatrix(**raw.get("capabilities", {}))

            return EnvironmentProfile(
                os_name=raw.get("os_name", ""),
                os_version=raw.get("os_version", ""),
                hostname=raw.get("hostname", ""),
                detected_at=raw.get("detected_at", ""),
                editor=raw.get("editor", "unknown"),
                installed_agents=raw.get("installed_agents", []),
                providers=providers,
                models=models,
                local_servers=raw.get("local_servers", []),
                mcp_servers=mcp_servers,
                ide_profiles=ide_profiles,
                capabilities=capabilities,
                scan_duration_ms=raw.get("scan_duration_ms", 0),
                errors=raw.get("errors", []),
            )
        except Exception:
            return None
