"""
Model Capability Profiler — benchmarks models when a user adds API keys.

Runs a short set of test prompts covering the 8 main task types.
Scores are heuristic (keyword presence + response coherence), not ground truth.
Full benchmarking would require real test datasets — this is a quick-start profile.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from backend.core.providers.schema import ModelProfile, PROVIDER_METADATA


# One short prompt per task type — designed to run fast (small max_tokens)
_BENCHMARK_PROMPTS: dict[str, dict] = {
    "code_review": {
        "prompt": "Review this Python function for bugs and style:\n```python\ndef get_user(id):\n  return db.query('SELECT * FROM users WHERE id='+str(id))\n```",
        "good_signals": ["sql injection", "parameterized", "f-string", "placeholder", "security"],
        "max_tokens": 200,
    },
    "architecture": {
        "prompt": "In 3 bullet points, what are the main concerns when designing a microservice that handles payments?",
        "good_signals": ["idempotent", "distributed", "retry", "saga", "eventual consistency", "fault", "circuit"],
        "max_tokens": 150,
    },
    "security": {
        "prompt": "List 3 OWASP Top 10 vulnerabilities that commonly affect REST APIs.",
        "good_signals": ["injection", "broken auth", "xss", "csrf", "exposure", "owasp", "vulnerability"],
        "max_tokens": 150,
    },
    "documentation": {
        "prompt": "Write a one-line Python docstring for: def calculate_tax(income: float, rate: float) -> float",
        "good_signals": ["income", "rate", "tax", "returns", "float", "calculate"],
        "max_tokens": 80,
    },
    "bug_fix": {
        "prompt": "Fix this buggy Python code:\n```python\ndef average(nums):\n    return sum(nums) / len(nums)\n```\nHint: it crashes on empty lists.",
        "good_signals": ["if", "len", "empty", "zero", "return 0", "None", "raise", "ZeroDivisionError"],
        "max_tokens": 100,
    },
    "testing": {
        "prompt": "Write a single pytest test for a function `add(a, b)` that returns a + b.",
        "good_signals": ["def test_", "assert", "add(", "pytest", "=="],
        "max_tokens": 100,
    },
    "refactor": {
        "prompt": "Suggest one refactoring for this code:\n```python\nif x == 1:\n    print('one')\nelif x == 2:\n    print('two')\nelif x == 3:\n    print('three')\n```",
        "good_signals": ["dict", "map", "match", "lookup", "table", "clean", "readable"],
        "max_tokens": 120,
    },
    "reasoning": {
        "prompt": "If it takes 5 machines 5 minutes to make 5 widgets, how long does it take 100 machines to make 100 widgets? Explain briefly.",
        "good_signals": ["5 minutes", "5 min", "same", "parallel", "each machine"],
        "max_tokens": 100,
    },
}


def _score_response(text: str, signals: list[str]) -> float:
    """Heuristic score 0–10 based on signal keyword hits + response length."""
    text_lower = text.lower()
    hits = sum(1 for s in signals if s.lower() in text_lower)
    signal_score = min(8.0, hits / max(len(signals), 1) * 10)
    # Reward non-trivial responses (at least 30 chars)
    length_bonus = min(2.0, len(text) / 100)
    return round(min(10.0, signal_score + length_bonus), 1)


class ModelProfiler:
    """
    Benchmark one or more models against the 8 task types.
    Writes results to ModelProfile table via ProviderStore.
    """

    def __init__(self, project_path: str, db_path: str):
        self.project_path = project_path
        self.db_path = db_path

    def profile_model(
        self,
        provider: str,
        model_id: str,
        api_key: Optional[str] = None,
        tasks: Optional[list[str]] = None,
    ) -> ModelProfile:
        from backend.llm.litellm_gateway import LiteLLMGateway

        gateway = LiteLLMGateway(project_path=self.project_path, db_path=self.db_path)
        task_list = tasks or list(_BENCHMARK_PROMPTS.keys())

        profile = ModelProfile(
            project_path=self.project_path,
            provider=provider,
            model_id=model_id,
        )

        latencies = []
        for task in task_list:
            cfg = _BENCHMARK_PROMPTS[task]
            try:
                resp = gateway.complete(
                    model=f"{provider}/{model_id}" if "/" not in model_id else model_id,
                    messages=[{"role": "user", "content": cfg["prompt"]}],
                    max_tokens=cfg["max_tokens"],
                    temperature=0.1,
                )
                score = _score_response(resp.text, cfg["good_signals"])
                setattr(profile, f"score_{task}", score)
                latencies.append(resp.latency_ms)

                if resp.cost_usd > 0 and resp.tokens_input > 0:
                    profile.cost_per_1k_input  = round(resp.cost_usd / resp.tokens_input * 1000, 6)
                    profile.cost_per_1k_output = round(resp.cost_usd / max(resp.tokens_output, 1) * 1000, 6)

            except Exception:
                pass

        if latencies:
            profile.avg_latency_ms = round(sum(latencies) / len(latencies), 1)

        # Populate known context windows from metadata
        known_ctx = {
            "anthropic/claude-opus-4-8":   200000,
            "anthropic/claude-sonnet-4-6": 200000,
            "openai/gpt-4o":              128000,
            "openai/gpt-4o-mini":         128000,
            "gemini/gemini-2.5-pro":     1000000,
            "groq/llama-3.3-70b-versatile": 128000,
            "deepseek/deepseek-chat":      64000,
        }
        full_id = f"{provider}/{model_id}"
        profile.context_window = known_ctx.get(full_id)

        return profile

    def profile_all_models(
        self,
        provider: str,
        model_ids: list[str],
        tasks: Optional[list[str]] = None,
    ) -> list[ModelProfile]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        profiles = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.profile_model, provider, m, tasks=tasks): m
                for m in model_ids
            }
            for fut in as_completed(futures):
                try:
                    profiles.append(fut.result())
                except Exception:
                    pass

        # Persist to DB
        try:
            from backend.core.providers.store import ProviderStore
            store = ProviderStore(db_path=self.db_path)
            store.init_db()
            for p in profiles:
                store.save_profile(p)
        except Exception:
            pass

        return profiles
