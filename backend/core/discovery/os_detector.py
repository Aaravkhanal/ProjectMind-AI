"""
OS & environment variable detector.

Scans the current process environment for known API key patterns
and returns DetectedProvider objects — no HTTP calls, purely local.
"""

from __future__ import annotations

import os
import platform
import socket
from typing import Optional

from .schema import DetectedModel, DetectedProvider

# provider → (env_var, display_label, default_models)
_ENV_PROVIDERS: dict[str, tuple[str, str, list[str]]] = {
    "openai":      ("OPENAI_API_KEY",       "OpenAI",       ["gpt-4o", "gpt-4o-mini", "o3-mini"]),
    "anthropic":   ("ANTHROPIC_API_KEY",    "Anthropic",    ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]),
    "google":      ("GEMINI_API_KEY",       "Google Gemini",["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash"]),
    "groq":        ("GROQ_API_KEY",         "Groq",         ["groq/llama-3.3-70b-versatile", "groq/llama-3.1-8b-instant"]),
    "deepseek":    ("DEEPSEEK_API_KEY",     "DeepSeek",     ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"]),
    "openrouter":  ("OPENROUTER_API_KEY",   "OpenRouter",   ["openrouter/auto"]),
    "together":    ("TOGETHER_API_KEY",     "Together AI",  ["together_ai/meta-llama/Llama-3-70b-chat-hf"]),
    "mistral":     ("MISTRAL_API_KEY",      "Mistral AI",   ["mistral/mistral-large-latest", "mistral/codestral-latest"]),
    "xai":         ("XAI_API_KEY",          "xAI",          ["xai/grok-3", "xai/grok-3-mini"]),
    "fireworks":   ("FIREWORKS_API_KEY",    "Fireworks AI", ["fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct"]),
    "nvidia":      ("NVIDIA_API_KEY",       "NVIDIA NIM",   ["nvidia_nim/meta/llama-3.1-70b-instruct"]),
    "cohere":      ("COHERE_API_KEY",       "Cohere",       ["command-r-plus"]),
    "huggingface": ("HUGGINGFACE_API_KEY",  "HuggingFace",  []),
    "azure":       ("AZURE_API_KEY",        "Azure OpenAI", []),
    "langfuse":    ("LANGFUSE_PUBLIC_KEY",  "Langfuse",     []),  # observability, not LLM
}

# Models for providers detected via env var (key metadata)
_PROVIDER_MODEL_METADATA: dict[str, dict] = {
    "openai": {
        "gpt-4o":               {"context_window": 128_000, "display_name": "GPT-4o"},
        "gpt-4o-mini":          {"context_window": 128_000, "display_name": "GPT-4o Mini"},
        "o3-mini":              {"context_window": 200_000, "display_name": "o3-mini"},
    },
    "anthropic": {
        "claude-sonnet-4-6":              {"context_window": 200_000, "display_name": "Claude Sonnet 4.6"},
        "claude-opus-4-8":               {"context_window": 200_000, "display_name": "Claude Opus 4.8"},
        "claude-haiku-4-5-20251001":     {"context_window": 200_000, "display_name": "Claude Haiku 4.5"},
    },
    "google": {
        "gemini/gemini-2.5-pro":   {"context_window": 1_000_000, "display_name": "Gemini 2.5 Pro"},
        "gemini/gemini-2.5-flash": {"context_window": 1_000_000, "display_name": "Gemini 2.5 Flash"},
    },
    "groq": {
        "groq/llama-3.3-70b-versatile": {"context_window": 128_000, "display_name": "Llama 3.3 70B (Groq)"},
        "groq/llama-3.1-8b-instant":    {"context_window": 128_000, "display_name": "Llama 3.1 8B (Groq)"},
    },
    "deepseek": {
        "deepseek/deepseek-chat":      {"context_window": 64_000, "display_name": "DeepSeek V3"},
        "deepseek/deepseek-reasoner":  {"context_window": 64_000, "display_name": "DeepSeek R1"},
    },
    "mistral": {
        "mistral/mistral-large-latest":  {"context_window": 128_000, "display_name": "Mistral Large"},
        "mistral/codestral-latest":      {"context_window": 256_000, "display_name": "Codestral"},
    },
    "xai": {
        "xai/grok-3":      {"context_window": 131_072, "display_name": "Grok-3"},
        "xai/grok-3-mini": {"context_window": 131_072, "display_name": "Grok-3 Mini"},
    },
}


def _key_preview(raw_key: str) -> str:
    if len(raw_key) >= 8:
        return raw_key[:4] + "****" + raw_key[-4:]
    return "****"


def detect_os() -> dict[str, str]:
    return {
        "os_name":    platform.system().lower(),   # "darwin" | "linux" | "windows"
        "os_version": platform.version(),
        "hostname":   socket.gethostname(),
        "python":     platform.python_version(),
        "arch":       platform.machine(),
    }


def detect_env_providers() -> tuple[list[DetectedProvider], list[DetectedModel]]:
    """
    Scan os.environ for known API key env vars.
    Returns (providers, models) tuples.
    Skips observability keys (Langfuse) from the models list.
    """
    providers: list[DetectedProvider] = []
    models: list[DetectedModel] = []

    for provider, (env_var, label, default_models) in _ENV_PROVIDERS.items():
        raw_key = os.environ.get(env_var, "").strip()
        if not raw_key:
            continue

        # Skip observability-only keys
        if provider in ("langfuse",):
            continue

        prov = DetectedProvider(
            provider=provider,
            label=label,
            source="env_var",
            has_key=True,
            key_preview=_key_preview(raw_key),
            models=list(default_models),
        )
        providers.append(prov)

        metadata = _PROVIDER_MODEL_METADATA.get(provider, {})
        for model_id in default_models:
            meta = metadata.get(model_id, {})
            models.append(DetectedModel(
                model_id=model_id,
                display_name=meta.get("display_name", model_id),
                provider=provider,
                source="env_var",
                is_local=False,
                is_free=False,
                context_window=meta.get("context_window"),
            ))

    return providers, models


def detect_claude_code_env() -> Optional[str]:
    """
    Return 'claude_code' if we appear to be running inside Claude Code.
    Checks known env markers Claude Code sets.
    """
    markers = [
        "CLAUDE_CODE",
        "CLAUDE_SESSION_ID",
        "CLAUDE_CODE_SESSION",
        "ANTHROPIC_CLAUDE_CODE",
        "CLAUDE_API_KEY",          # Claude Code injects this
    ]
    for m in markers:
        if os.environ.get(m):
            return "claude_code"

    # Check parent process name heuristic
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("Name:") and "claude" in line.lower():
                    return "claude_code"
    except Exception:
        pass

    return None
