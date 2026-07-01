"""
ModelRouter — automatically selects the best model for a given task.

Logic:
  1. classify_task()  → TaskComplexity  (heuristic, no LLM call needed)
  2. select_model()   → ModelConfig     (picks from available models)
  3. explain()        → str             (human-readable reason)

The router prefers models whose provider keys are present in the environment,
so it never recommends a model you can't actually use.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from backend.llm.catalog import (
    ALL_MODELS,
    ModelConfig,
    ModelTier,
    TaskComplexity,
)


# ── Keyword signals ────────────────────────────────────────────────────────────

_COMPLEX_KEYWORDS = {
    "architecture", "refactor", "redesign", "restructure", "migration",
    "security", "vulnerability", "audit", "cve", "authentication", "authorization",
    "database", "schema", "orm", "performance", "scalability", "concurrency",
    "microservice", "monolith", "distributed", "race condition", "deadlock",
}

_MEDIUM_KEYWORDS = {
    "review", "bug", "fix", "error", "exception", "test", "coverage",
    "documentation", "docstring", "type hint", "api", "endpoint",
    "validation", "logging", "monitoring",
}

_SIMPLE_KEYWORDS = {
    "rename", "format", "style", "typo", "comment", "whitespace",
    "import", "variable", "constant", "print", "log message",
}

# Agent role → preferred tier
_AGENT_TIER: dict[str, ModelTier] = {
    "architect":    ModelTier.POWERFUL,
    "security":     ModelTier.REASONING,
    "quality":      ModelTier.BALANCED,
    "planner":      ModelTier.BALANCED,
    "synthesizer":  ModelTier.BALANCED,
    "refactor":     ModelTier.POWERFUL,
    "testing":      ModelTier.BALANCED,
    "docs":         ModelTier.FAST,
}

# Provider → env var that must be non-empty to use it
_PROVIDER_ENV: dict[str, str] = {
    "nvidia":    "API_KEY",
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GOOGLE_API_KEY",
    "deepseek":  "DEEPSEEK_API_KEY",
    "ollama":    "",               # always available if Ollama is running
}


@dataclass
class RoutingDecision:
    model: ModelConfig
    complexity: TaskComplexity
    reason: str
    estimated_cost_usd: float
    alternatives: list[ModelConfig]


# ── Availability check ─────────────────────────────────────────────────────────

def _available_providers() -> set[str]:
    """Returns the set of providers whose API keys are present in the environment."""
    available = set()
    for provider, env_var in _PROVIDER_ENV.items():
        if not env_var:
            available.add(provider)  # ollama, always try
        elif os.environ.get(env_var, "").strip():
            available.add(provider)
    return available


def _available_models() -> list[ModelConfig]:
    providers = _available_providers()
    return [m for m in ALL_MODELS if m.provider in providers]


# ── Task classification ────────────────────────────────────────────────────────

def classify_task(
    description: str = "",
    diff: str = "",
    file_count: int = 0,
) -> TaskComplexity:
    """
    Classify task complexity from heuristics — no LLM call, instant.

    Priority: keyword signals > diff size > file count
    """
    text = (description + " " + diff[:2000]).lower()

    complex_hits = sum(1 for kw in _COMPLEX_KEYWORDS if kw in text)
    medium_hits  = sum(1 for kw in _MEDIUM_KEYWORDS  if kw in text)
    simple_hits  = sum(1 for kw in _SIMPLE_KEYWORDS  if kw in text)

    diff_lines = len(diff.splitlines())

    # Score: each keyword hit = 2 pts, each 100 diff lines = 1 pt, each file = 0.5 pt
    complex_score = complex_hits * 2 + max(0, (diff_lines - 300) // 100) + max(0, file_count - 10) * 0.5
    medium_score  = medium_hits  * 2 + max(0, (diff_lines - 50)  // 100) + max(0, file_count - 3)  * 0.5
    simple_score  = simple_hits  * 2

    if complex_score >= 3:
        return TaskComplexity.COMPLEX
    if medium_score >= 2 or diff_lines > 200:
        return TaskComplexity.MEDIUM
    if diff_lines > 50:
        return TaskComplexity.MEDIUM
    return TaskComplexity.SIMPLE


# ── Tier selection per complexity ──────────────────────────────────────────────

_COMPLEXITY_TO_TIERS: dict[TaskComplexity, list[ModelTier]] = {
    TaskComplexity.SIMPLE:  [ModelTier.FAST, ModelTier.BALANCED],
    TaskComplexity.MEDIUM:  [ModelTier.BALANCED, ModelTier.POWERFUL],
    TaskComplexity.COMPLEX: [ModelTier.REASONING, ModelTier.POWERFUL, ModelTier.BALANCED],
}


# ── Main router ────────────────────────────────────────────────────────────────

class ModelRouter:
    """
    Selects the best available model for a task.

    Usage:
        router = ModelRouter()
        decision = router.route(description="refactor auth module", diff=diff_text)
        print(decision.model.model_id, decision.reason)

    Per-agent selection:
        model = router.route_for_agent("security", complexity=TaskComplexity.COMPLEX).model
    """

    def __init__(self, preferred_provider: str | None = None, budget_per_task_usd: float = 1.0):
        self.preferred_provider = preferred_provider or os.environ.get("LLM_PROVIDER", "nvidia")
        self.budget_per_task_usd = budget_per_task_usd
        self._available = _available_models()

    def route(
        self,
        description: str = "",
        diff: str = "",
        file_count: int = 0,
        force_complexity: TaskComplexity | None = None,
    ) -> RoutingDecision:
        complexity = force_complexity or classify_task(description, diff, file_count)
        return self._pick(complexity, agent_role=None)

    def route_for_agent(
        self,
        agent_role: str,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
    ) -> RoutingDecision:
        """
        Select the best model for a specific agent role.
        Each agent has a preferred tier — e.g. security agent prefers reasoning models.
        """
        preferred_tier = _AGENT_TIER.get(agent_role, ModelTier.BALANCED)

        # If task is simple, cap at BALANCED even for powerful-preferring agents
        if complexity == TaskComplexity.SIMPLE and preferred_tier == ModelTier.POWERFUL:
            preferred_tier = ModelTier.BALANCED
        if complexity == TaskComplexity.SIMPLE and preferred_tier == ModelTier.REASONING:
            preferred_tier = ModelTier.BALANCED

        return self._pick(complexity, agent_role=agent_role, override_tier=preferred_tier)

    def _pick(
        self,
        complexity: TaskComplexity,
        agent_role: str | None,
        override_tier: ModelTier | None = None,
    ) -> RoutingDecision:
        tiers = [override_tier] if override_tier else _COMPLEXITY_TO_TIERS[complexity]

        candidates: list[ModelConfig] = []
        for tier in tiers:
            tier_models = [m for m in self._available if m.tier == tier]
            # Preferred provider first
            preferred = [m for m in tier_models if m.provider == self.preferred_provider]
            others    = [m for m in tier_models if m.provider != self.preferred_provider]
            candidates.extend(preferred + others)
            if candidates:
                break

        if not candidates:
            # Last resort: any available model
            candidates = self._available or _fallback_model()

        # Apply budget filter — remove models that'd blow the budget on a typical task
        within_budget = [
            m for m in candidates
            if self._estimate_cost(m, diff_lines=300) <= self.budget_per_task_usd
        ]
        chosen = (within_budget or candidates)[0]
        alternatives = [m for m in candidates if m.model_id != chosen.model_id][:3]

        return RoutingDecision(
            model=chosen,
            complexity=complexity,
            reason=self._explain(chosen, complexity, agent_role),
            estimated_cost_usd=self._estimate_cost(chosen),
            alternatives=alternatives,
        )

    @staticmethod
    def _estimate_cost(model: ModelConfig, diff_lines: int = 300) -> float:
        # Rough estimate: 300 diff lines ≈ 2000 input tokens + 800 output tokens
        input_tokens  = max(diff_lines * 6, 1000)
        output_tokens = max(diff_lines * 2, 400)
        return (
            (input_tokens  / 1000) * model.cost_per_1k_input +
            (output_tokens / 1000) * model.cost_per_1k_output
        )

    @staticmethod
    def _explain(model: ModelConfig, complexity: TaskComplexity, agent_role: str | None) -> str:
        role_str = f" for the {agent_role} agent" if agent_role else ""
        strengths = ", ".join(model.strengths[:3]) if model.strengths else "general purpose"
        return (
            f"Selected **{model.display_name}** ({model.provider}){role_str}. "
            f"Task complexity: {complexity.value}. "
            f"Model tier: {model.tier.value}. "
            f"Key strengths: {strengths}. "
            f"Est. cost: ~${ModelRouter._estimate_cost(model):.4f} per review."
        )

    def route_all_agents(
        self,
        complexity: TaskComplexity,
    ) -> dict[str, RoutingDecision]:
        """Return routing decisions for every agent role at once."""
        return {
            role: self.route_for_agent(role, complexity)
            for role in _AGENT_TIER
        }


def _fallback_model() -> list[ModelConfig]:
    """Always works — uses whatever is in the environment."""
    provider = os.environ.get("LLM_PROVIDER", "nvidia")
    model_id = os.environ.get("CODE_MODEL", "meta/llama-3.1-8b-instruct")
    return [ModelConfig(
        provider=provider,
        model_id=model_id,
        display_name=model_id,
        tier=ModelTier.BALANCED,
        context_window=128_000,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.001,
    )]
