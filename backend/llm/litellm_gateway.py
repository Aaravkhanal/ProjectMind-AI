"""
LiteLLM Gateway — universal interface to 100+ LLM providers.

Wraps litellm.completion() to:
  1. Auto-resolve API keys from ProviderStore (BYOK) or environment
  2. Normalize model IDs to LiteLLM format (provider/model-id)
  3. Track cost/tokens via CostStore
  4. Langfuse tracing (if configured)
  5. Retry on rate-limit with exponential backoff

Usage:
    gateway = LiteLLMGateway(project_path=".")
    response = gateway.complete(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.text, response.cost_usd)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# LiteLLM normalizes ALL providers to OpenAI format
import litellm

litellm.drop_params = True   # ignore unsupported params silently
litellm.set_verbose = False


# ── Model ID normalization ─────────────────────────────────────────────────────

_MODEL_ALIASES: dict[str, str] = {
    # Anthropic
    "claude-opus-4-8":            "anthropic/claude-opus-4-8",
    "claude-sonnet-4-6":          "anthropic/claude-sonnet-4-6",
    "claude-haiku-4-5-20251001":  "anthropic/claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022": "anthropic/claude-3-5-sonnet-20241022",
    # OpenAI
    "gpt-4o":        "openai/gpt-4o",
    "gpt-4o-mini":   "openai/gpt-4o-mini",
    "gpt-4-turbo":   "openai/gpt-4-turbo",
    "o1":            "openai/o1",
    "o3-mini":       "openai/o3-mini",
    # Google
    "gemini-2.5-pro":   "gemini/gemini-2.5-pro",
    "gemini-2.5-flash": "gemini/gemini-2.5-flash",
    "gemini-1.5-pro":   "gemini/gemini-1.5-pro",
    # Groq
    "llama-3.3-70b":    "groq/llama-3.3-70b-versatile",
    "llama-3.1-8b":     "groq/llama-3.1-8b-instant",
    # DeepSeek
    "deepseek-chat":     "deepseek/deepseek-chat",
    "deepseek-reasoner": "deepseek/deepseek-reasoner",
    # Ollama (local)
    "llama3.2":           "ollama/llama3.2",
    "qwen2.5-coder":      "ollama/qwen2.5-coder",
    "deepseek-coder-v2":  "ollama/deepseek-coder-v2",
    # xAI
    "grok-3":     "xai/grok-3",
    "grok-3-mini":"xai/grok-3-mini",
    # Mistral
    "mistral-large": "mistral/mistral-large-latest",
    "codestral":     "mistral/codestral-latest",
}

_PROVIDER_ENV_KEYS: dict[str, str] = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "groq":       "GROQ_API_KEY",
    "deepseek":   "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together":   "TOGETHER_API_KEY",
    "mistral":    "MISTRAL_API_KEY",
    "xai":        "XAI_API_KEY",
    "fireworks":  "FIREWORKS_API_KEY",
    "nvidia":     "NVIDIA_API_KEY",
    "huggingface":"HUGGINGFACE_API_KEY",
}


def _resolve_model(model_id: str) -> str:
    """Convert short alias to litellm provider/model format."""
    if "/" in model_id:
        return model_id
    return _MODEL_ALIASES.get(model_id, model_id)


@dataclass
class CompletionResponse:
    text: str
    model: str
    provider: str
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    raw: Any = field(default=None, repr=False)


class LiteLLMGateway:
    """
    Universal LLM gateway.

    - Resolves API keys from ProviderStore (BYOK) or environment
    - Maps short model names to provider/model strings
    - Tracks cost via litellm.completion_cost()
    - Langfuse tracing if LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY are set
    """

    def __init__(
        self,
        project_path: str = ".",
        db_path: Optional[str] = None,
    ):
        self.project_path = project_path
        self._db_path = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
        self._langfuse = self._init_langfuse()

    def _init_langfuse(self):
        if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse.callback import CallbackHandler
                return CallbackHandler()
            except ImportError:
                pass
        return None

    def _get_api_key(self, provider: str) -> Optional[str]:
        """Get API key from BYOK store first, then environment."""
        try:
            from backend.core.providers.store import ProviderStore
            store = ProviderStore(db_path=self._db_path)
            store.init_db()
            return store.get_api_key(self.project_path, provider)
        except Exception:
            pass
        env_key = _PROVIDER_ENV_KEYS.get(provider)
        return os.environ.get(env_key, "") if env_key else None

    def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stream: bool = False,
        extra_kwargs: Optional[dict] = None,
    ) -> CompletionResponse:
        """
        Call any LLM model through LiteLLM.

        model can be:
          - "claude-sonnet-4-6"              (alias)
          - "anthropic/claude-sonnet-4-6"    (explicit)
          - "gpt-4o"                         (alias)
          - "ollama/llama3.2"               (local)
          - "openrouter/openai/gpt-4o"       (via OpenRouter)
        """
        resolved = _resolve_model(model)
        provider = resolved.split("/")[0] if "/" in resolved else "unknown"
        api_key  = self._get_api_key(provider)

        # Resolve base_url for local/custom providers
        base_url = None
        if provider == "ollama":
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        elif provider == "lmstudio":
            base_url = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
            resolved = resolved.replace("lmstudio/", "openai/")  # LM Studio is OpenAI-compatible
        elif provider == "vllm":
            base_url = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
            resolved = resolved.replace("vllm/", "openai/")
        elif provider == "nvidia":
            base_url = "https://integrate.api.nvidia.com/v1"
            resolved = resolved.replace("nvidia/", "openai/")

        kwargs: dict[str, Any] = {
            "model":       resolved,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      stream,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        t0 = time.time()
        retries = 2
        for attempt in range(retries + 1):
            try:
                response = litellm.completion(**kwargs)
                break
            except litellm.RateLimitError:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                else:
                    raise
            except litellm.AuthenticationError as e:
                raise RuntimeError(f"Auth error for provider '{provider}': {e}") from e

        latency_ms = (time.time() - t0) * 1000
        text = response.choices[0].message.content or ""

        # Cost estimation via litellm
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            cost = 0.0

        usage = response.usage or {}
        return CompletionResponse(
            text=text,
            model=resolved,
            provider=provider,
            tokens_input=getattr(usage, "prompt_tokens", 0),
            tokens_output=getattr(usage, "completion_tokens", 0),
            cost_usd=cost,
            latency_ms=latency_ms,
            raw=response,
        )

    def complete_parallel(
        self,
        model_list: list[str],
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> list[CompletionResponse]:
        """
        Call multiple models in parallel.
        Used for Debate Mode and Voting Mode.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[CompletionResponse] = [None] * len(model_list)  # type: ignore

        def _call(idx: int, model: str) -> tuple[int, CompletionResponse]:
            resp = self.complete(model, messages, temperature=temperature, max_tokens=max_tokens)
            return idx, resp

        with ThreadPoolExecutor(max_workers=len(model_list)) as executor:
            futures = {executor.submit(_call, i, m): i for i, m in enumerate(model_list)}
            for fut in as_completed(futures):
                try:
                    idx, resp = fut.result()
                    results[idx] = resp
                except Exception as e:
                    idx = futures[fut]
                    results[idx] = CompletionResponse(
                        text=f"[ERROR: {e}]", model=model_list[idx], provider="unknown"
                    )

        return results

    def test_provider(self, provider: str, api_key: Optional[str] = None) -> dict:
        """
        Validate a provider's API key with a minimal call.
        Returns {"ok": bool, "latency_ms": float, "error": str | None}
        """
        meta_models = {
            "openai": "openai/gpt-4o-mini", "anthropic": "anthropic/claude-haiku-4-5-20251001",
            "google": "gemini/gemini-2.5-flash", "groq": "groq/llama-3.1-8b-instant",
            "deepseek": "deepseek/deepseek-chat", "mistral": "mistral/mistral-small-latest",
            "xai": "xai/grok-3-mini", "ollama": "ollama/llama3.2", "nvidia": "openai/meta/llama-3.1-8b-instruct",
        }
        test_model = meta_models.get(provider, f"{provider}/{provider}-default")
        try:
            resp = self.complete(
                model=test_model,
                messages=[{"role": "user", "content": "Say 'ok' in 3 words."}],
                max_tokens=10,
                temperature=0,
            )
            return {"ok": True, "latency_ms": resp.latency_ms, "error": None, "model_tested": test_model}
        except Exception as e:
            return {"ok": False, "latency_ms": 0, "error": str(e), "model_tested": test_model}
