"""
Phase 20 — Environment-Aware Model Discovery API.

Endpoints:
  GET  /discover/scan          — run a fresh full environment scan
  GET  /discover/profile       — return cached profile (scan if none)
  GET  /discover/models        — all discovered models
  GET  /discover/providers     — all detected providers
  GET  /discover/capabilities  — capability matrix (task → best model)
  GET  /discover/mcp           — all detected MCP servers
  POST /discover/register      — register a custom model endpoint
  POST /discover/import        — auto-import detected providers into ProviderStore
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from backend.core.discovery.profiler import EnvironmentProfiler
from backend.core.discovery.schema import DetectedModel, DetectedProvider, EnvironmentProfile

router = APIRouter(prefix="/discover", tags=["environment-discovery"])


def _profiler(project_path: str) -> EnvironmentProfiler:
    return EnvironmentProfiler(project_path=project_path)


def _profile_or_scan(project_path: str) -> EnvironmentProfile:
    p = _profiler(project_path)
    cached = p.load_cached()
    return cached if cached else p.scan()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/scan")
async def scan_environment(
    project_path: Annotated[str, Query()] = ".",
    force: Annotated[bool, Query()] = False,
):
    """
    Run a full environment scan. Returns the complete EnvironmentProfile.
    Set force=true to bypass the cache even if a recent scan exists.
    """
    p = _profiler(project_path)
    if not force:
        cached = p.load_cached()
        if cached:
            return {
                "source": "cache",
                "scanned_at": cached.detected_at,
                "profile": cached.to_dict(),
                "summary": _summarize(cached),
            }

    profile = p.scan()
    return {
        "source": "fresh_scan",
        "scanned_at": profile.detected_at,
        "scan_duration_ms": round(profile.scan_duration_ms, 1),
        "profile": profile.to_dict(),
        "summary": _summarize(profile),
    }


@router.get("/profile")
async def get_profile(project_path: Annotated[str, Query()] = "."):
    """Return the cached profile (triggers a scan if no cache exists)."""
    profile = _profile_or_scan(project_path)
    return profile.to_dict()


@router.get("/models")
async def list_discovered_models(
    project_path: Annotated[str, Query()] = ".",
    local_only: Annotated[bool, Query()] = False,
    free_only: Annotated[bool, Query()] = False,
):
    """List all discovered models, optionally filtered."""
    profile = _profile_or_scan(project_path)
    models = profile.models
    if local_only:
        models = [m for m in models if m.is_local]
    if free_only:
        models = [m for m in models if m.is_free]
    return {
        "total": len(models),
        "local_count": sum(1 for m in profile.models if m.is_local),
        "cloud_count": sum(1 for m in profile.models if not m.is_local),
        "models": [_model_dict(m) for m in models],
    }


@router.get("/providers")
async def list_discovered_providers(project_path: Annotated[str, Query()] = "."):
    """List all providers detected in this environment."""
    profile = _profile_or_scan(project_path)
    return {
        "total": len(profile.providers),
        "providers": [_provider_dict(p) for p in profile.providers],
    }


@router.get("/capabilities")
async def get_capability_matrix(project_path: Annotated[str, Query()] = "."):
    """
    Returns the capability matrix — which model is best for each task type.
    This is what the intelligent task router uses.
    """
    profile = _profile_or_scan(project_path)
    caps = profile.capabilities
    from dataclasses import asdict
    return {
        "editor": profile.editor,
        "provider_count": len(profile.providers),
        "model_count": len(profile.models),
        "capabilities": asdict(caps),
        "routing_table": {
            "architecture": caps.best_architecture,
            "coding":       caps.best_coding,
            "security":     caps.best_security,
            "review":       caps.best_review,
            "testing":      caps.best_testing,
            "documentation": caps.best_documentation,
            "bug_fix":      caps.best_bug_fix,
            "reasoning":    caps.best_reasoning,
            "long_context": caps.best_long_context,
            "fastest":      caps.fastest,
            "cheapest":     caps.cheapest,
            "default":      caps.default_model,
        },
    }


@router.get("/mcp")
async def list_mcp_servers(project_path: Annotated[str, Query()] = "."):
    """List all detected MCP servers across all config sources."""
    profile = _profile_or_scan(project_path)
    from dataclasses import asdict
    return {
        "total": len(profile.mcp_servers),
        "servers": [asdict(s) for s in profile.mcp_servers],
    }


@router.post("/register")
async def register_custom_model(
    project_path: Annotated[str, Query()] = ".",
    body: dict = None,
):
    """
    Register a custom OpenAI-compatible API endpoint.

    Body: {"provider": "my-company-llm", "endpoint": "https://...", "model": "company-coder-v1"}
    """
    if body is None:
        body = {}

    provider = body.get("provider", "").strip()
    endpoint = body.get("endpoint", "").strip()
    model_id = body.get("model", "").strip()

    if not provider or not endpoint or not model_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="provider, endpoint, and model are required")

    registry_path = Path(project_path) / ".projectmind" / "custom_models.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if registry_path.exists():
        try:
            existing = json.loads(registry_path.read_text())
        except Exception:
            pass

    # Upsert
    existing = [e for e in existing if not (e.get("provider") == provider and e.get("model") == model_id)]
    existing.append({"provider": provider, "endpoint": endpoint, "model": model_id})
    registry_path.write_text(json.dumps(existing, indent=2))

    return {"registered": True, "provider": provider, "model": model_id, "endpoint": endpoint}


@router.post("/import")
async def import_detected_providers(
    project_path: Annotated[str, Query()] = ".",
    background_tasks: BackgroundTasks = None,
):
    """
    Auto-import all detected providers with env-var API keys into the
    encrypted ProviderStore so BYOK features can use them immediately.
    """
    profile = _profile_or_scan(project_path)

    from backend.core.providers.store import ProviderStore
    store = ProviderStore()
    imported: list[str] = []
    skipped: list[str] = []

    import os
    from backend.core.providers.schema import PROVIDER_METADATA

    for detected in profile.providers:
        if detected.source != "env_var":
            skipped.append(detected.provider)
            continue

        meta = PROVIDER_METADATA.get(detected.provider, {})
        env_key = meta.get("key_env", "")
        raw_key = os.environ.get(env_key, "")
        if not raw_key:
            skipped.append(detected.provider)
            continue

        try:
            store.add_provider(
                project_path=project_path,
                provider=detected.provider,
                api_key=raw_key,
            )
            imported.append(detected.provider)
        except Exception:
            skipped.append(detected.provider)

    return {
        "imported": imported,
        "skipped": skipped,
        "total_providers": len(profile.providers),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize(profile: EnvironmentProfile) -> dict:
    return {
        "editor": profile.editor,
        "installed_agents": profile.installed_agents,
        "providers": profile.provider_names,
        "local_servers": profile.local_servers,
        "model_count": len(profile.models),
        "mcp_count": len(profile.mcp_servers),
        "default_model": profile.capabilities.default_model,
        "errors": profile.errors,
    }


def _model_dict(m: DetectedModel) -> dict:
    return {
        "model_id": m.model_id,
        "display_name": m.display_name,
        "provider": m.provider,
        "source": m.source,
        "is_local": m.is_local,
        "is_free": m.is_free,
        "context_window": m.context_window,
        "endpoint": m.endpoint,
    }


def _provider_dict(p: DetectedProvider) -> dict:
    return {
        "provider": p.provider,
        "label": p.label,
        "source": p.source,
        "has_key": p.has_key,
        "key_preview": p.key_preview,
        "model_count": len(p.models),
    }
