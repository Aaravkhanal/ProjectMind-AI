"""
Local model server detector.

Probes well-known ports for Ollama, LM Studio, llama.cpp, and vLLM.
All calls have short timeouts so startup stays fast even if servers are down.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .schema import DetectedModel, DetectedProvider

_TIMEOUT = 2  # seconds per probe


def _get_json(url: str) -> Optional[dict | list]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ollama  (default: localhost:11434)
# ---------------------------------------------------------------------------

def detect_ollama(host: str = "localhost", port: int = 11434) -> tuple[list[DetectedModel], Optional[DetectedProvider]]:
    base = f"http://{host}:{port}"
    data = _get_json(f"{base}/api/tags")
    if data is None:
        return [], None

    models: list[DetectedModel] = []
    model_ids: list[str] = []

    for m in data.get("models", []):
        raw_name = m.get("name", "")
        if not raw_name:
            continue
        model_id = f"ollama/{raw_name}"
        model_ids.append(model_id)

        details = m.get("details", {})
        param_size = details.get("parameter_size", "")
        ctx = _ollama_context(details)

        models.append(DetectedModel(
            model_id=model_id,
            display_name=f"{raw_name} (Ollama{' · ' + param_size if param_size else ''})",
            provider="ollama",
            source="ollama",
            is_local=True,
            is_free=True,
            context_window=ctx,
            endpoint=base,
        ))

    if not models:
        return [], None

    provider = DetectedProvider(
        provider="ollama",
        label="Ollama (local)",
        source="ollama",
        has_key=False,
        key_preview="(no key)",
        models=model_ids,
    )
    return models, provider


def _ollama_context(details: dict) -> Optional[int]:
    # Ollama doesn't expose context in /api/tags, infer from family
    family = details.get("family", "").lower()
    _CTX = {"llama3": 128_000, "llama2": 4096, "mistral": 32_768, "gemma": 8192, "phi": 4096}
    return next((v for k, v in _CTX.items() if k in family), None)


# ---------------------------------------------------------------------------
# LM Studio  (default: localhost:1234, OpenAI-compatible)
# ---------------------------------------------------------------------------

def detect_lmstudio(host: str = "localhost", port: int = 1234) -> tuple[list[DetectedModel], Optional[DetectedProvider]]:
    base = f"http://{host}:{port}"
    data = _get_json(f"{base}/v1/models")
    if data is None:
        return [], None

    model_list = data.get("data", data) if isinstance(data, dict) else data
    models: list[DetectedModel] = []
    model_ids: list[str] = []

    for m in model_list:
        raw_id = m.get("id", "") if isinstance(m, dict) else str(m)
        if not raw_id:
            continue
        model_id = f"lmstudio/{raw_id}"
        model_ids.append(model_id)
        models.append(DetectedModel(
            model_id=model_id,
            display_name=f"{raw_id} (LM Studio)",
            provider="lmstudio",
            source="lmstudio",
            is_local=True,
            is_free=True,
            endpoint=base,
        ))

    if not models:
        return [], None

    provider = DetectedProvider(
        provider="lmstudio",
        label="LM Studio (local)",
        source="lmstudio",
        has_key=False,
        key_preview="(no key)",
        models=model_ids,
    )
    return models, provider


# ---------------------------------------------------------------------------
# vLLM  (default: localhost:8000, OpenAI-compatible)
# ---------------------------------------------------------------------------

def detect_vllm(host: str = "localhost", port: int = 8000) -> tuple[list[DetectedModel], Optional[DetectedProvider]]:
    base = f"http://{host}:{port}"
    data = _get_json(f"{base}/v1/models")
    if data is None:
        return [], None

    model_list = data.get("data", []) if isinstance(data, dict) else []
    models: list[DetectedModel] = []
    model_ids: list[str] = []

    for m in model_list:
        raw_id = m.get("id", "")
        if not raw_id:
            continue
        model_id = f"vllm/{raw_id}"
        model_ids.append(model_id)
        models.append(DetectedModel(
            model_id=model_id,
            display_name=f"{raw_id} (vLLM)",
            provider="vllm",
            source="vllm",
            is_local=True,
            is_free=True,
            endpoint=base,
        ))

    if not models:
        return [], None

    provider = DetectedProvider(
        provider="vllm",
        label="vLLM (self-hosted)",
        source="vllm",
        has_key=False,
        key_preview="(no key)",
        models=model_ids,
    )
    return models, provider


# ---------------------------------------------------------------------------
# llama.cpp server  (default: localhost:8080, OpenAI-compatible)
# ---------------------------------------------------------------------------

def detect_llamacpp(host: str = "localhost", port: int = 8080) -> tuple[list[DetectedModel], Optional[DetectedProvider]]:
    base = f"http://{host}:{port}"
    # llama.cpp exposes /health and /v1/models
    health = _get_json(f"{base}/health")
    if health is None:
        return [], None

    # Try to get model name from /props
    props = _get_json(f"{base}/props") or {}
    model_name = props.get("default_generation_settings", {}).get("model", "llama.cpp-model")
    model_id = f"llamacpp/{model_name}"

    model = DetectedModel(
        model_id=model_id,
        display_name=f"{model_name} (llama.cpp)",
        provider="llamacpp",
        source="llamacpp",
        is_local=True,
        is_free=True,
        endpoint=base,
    )
    provider = DetectedProvider(
        provider="llamacpp",
        label="llama.cpp (local)",
        source="llamacpp",
        has_key=False,
        key_preview="(no key)",
        models=[model_id],
    )
    return [model], provider


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all_local() -> tuple[list[DetectedModel], list[DetectedProvider], list[str]]:
    """
    Probe all known local server ports.
    Returns (models, providers, active_server_names).
    """
    all_models: list[DetectedModel] = []
    all_providers: list[DetectedProvider] = []
    active: list[str] = []

    for name, fn in [
        ("ollama",    detect_ollama),
        ("lmstudio",  detect_lmstudio),
        ("vllm",      detect_vllm),
        ("llamacpp",  detect_llamacpp),
    ]:
        try:
            models, provider = fn()
            if provider:
                all_models.extend(models)
                all_providers.append(provider)
                active.append(name)
        except Exception:
            pass

    return all_models, all_providers, active
