"""
CostOptimizer — picks the cheapest model that still meets a quality bar.

Strategy:
  1. Check remaining budget for the project
  2. If remaining >= full cost estimate  → use the normally routed model
  3. If remaining < full cost estimate   → downgrade to next cheaper tier
  4. If budget is exhausted + hard_limit → raise BudgetExceededError
  5. Tracks every decision (downgraded or not) via CostStore

This integrates with ModelRouter from Phase 1 — the optimizer wraps the
router and applies budget constraints on top.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from backend.llm.catalog import ModelConfig, ModelTier
from backend.llm.router import ModelRouter, RoutingDecision, TaskComplexity, _available_models


class BudgetExceededError(Exception):
    """Raised when hard_limit=True and the budget is exhausted."""


@dataclass
class OptimizedDecision:
    model: ModelConfig
    agent_role: str
    complexity: TaskComplexity
    estimated_cost_usd: float
    was_downgraded: bool
    original_model: Optional[ModelConfig]   # None if no downgrade happened
    reason: str
    budget_remaining: Optional[float]


# Tier downgrade chain: if REASONING is too expensive, try POWERFUL, etc.
_DOWNGRADE_ORDER: list[ModelTier] = [
    ModelTier.REASONING,
    ModelTier.POWERFUL,
    ModelTier.BALANCED,
    ModelTier.FAST,
]


class CostOptimizer:
    """
    Wraps ModelRouter with budget awareness.

    Usage:
        optimizer = CostOptimizer(project_path=".", db_path=".projectmind/memory.db")
        decision  = optimizer.optimize_for_agent("security", TaskComplexity.COMPLEX)
        # decision.was_downgraded == True means budget forced a cheaper model
    """

    def __init__(
        self,
        project_path: str = ".",
        db_path: Optional[str] = None,
        preferred_provider: Optional[str] = None,
    ):
        self.project_path = project_path
        self._db_path = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
        self._preferred_provider = preferred_provider or os.environ.get("LLM_PROVIDER", "nvidia")
        self._budget = self._load_budget()

    def _load_budget(self):
        try:
            from backend.core.cost.store import CostStore
            store = CostStore(db_path=self._db_path)
            store.init_db()
            return store.get_budget(self.project_path)
        except Exception:
            return None

    def _remaining_budget(self) -> Optional[float]:
        if not self._budget:
            return None
        try:
            from backend.core.cost.store import CostStore
            store = CostStore(db_path=self._db_path)
            spend = store.get_spend(self.project_path)
            return max(0.0, self._budget.monthly_limit_usd - spend)
        except Exception:
            return None

    def optimize_for_agent(
        self,
        agent_role: str,
        complexity: TaskComplexity,
        per_call_budget_override: Optional[float] = None,
    ) -> OptimizedDecision:
        """
        Return the best model for this agent, respecting budget constraints.
        If no budget is configured, behaves exactly like ModelRouter.
        """
        remaining = per_call_budget_override or self._remaining_budget()

        # No budget constraint → plain routing
        if remaining is None:
            router   = ModelRouter(preferred_provider=self._preferred_provider)
            decision = router.route_for_agent(agent_role, complexity)
            return OptimizedDecision(
                model=decision.model,
                agent_role=agent_role,
                complexity=complexity,
                estimated_cost_usd=decision.estimated_cost_usd,
                was_downgraded=False,
                original_model=None,
                reason=decision.reason,
                budget_remaining=None,
            )

        # Hard limit exceeded
        if remaining <= 0 and self._budget and self._budget.hard_limit:
            raise BudgetExceededError(
                f"Monthly budget exhausted for {self.project_path}. "
                f"Limit: ${self._budget.monthly_limit_usd:.2f}"
            )

        # Try normal routing first
        router   = ModelRouter(preferred_provider=self._preferred_provider)
        decision = router.route_for_agent(agent_role, complexity)
        ideal    = decision.model

        # If the ideal model fits in budget, use it
        if decision.estimated_cost_usd <= remaining:
            return OptimizedDecision(
                model=ideal,
                agent_role=agent_role,
                complexity=complexity,
                estimated_cost_usd=decision.estimated_cost_usd,
                was_downgraded=False,
                original_model=None,
                reason=decision.reason,
                budget_remaining=remaining,
            )

        # Budget too tight — walk down the tier ladder to find something affordable
        available = _available_models()
        fallback_tier_name = (
            self._budget.fallback_tier if self._budget else "fast"
        )

        # Find the cheapest model in fallback tier from the preferred provider
        downgraded_model: Optional[ModelConfig] = None
        for tier in _DOWNGRADE_ORDER:
            tier_models = [
                m for m in available
                if m.tier == tier
                and ModelRouter._estimate_cost(m) <= remaining
            ]
            if tier_models:
                # Prefer same provider, then cheapest
                preferred = [m for m in tier_models if m.provider == self._preferred_provider]
                pool = preferred or tier_models
                downgraded_model = min(pool, key=lambda m: ModelRouter._estimate_cost(m))
                break

        if downgraded_model is None:
            # Nothing fits — use absolute cheapest available
            if available:
                downgraded_model = min(available, key=lambda m: ModelRouter._estimate_cost(m))
            else:
                # Last resort: use ideal model anyway (budget exceeded but not hard limit)
                return OptimizedDecision(
                    model=ideal,
                    agent_role=agent_role,
                    complexity=complexity,
                    estimated_cost_usd=decision.estimated_cost_usd,
                    was_downgraded=False,
                    original_model=None,
                    reason="No affordable model found — using ideal despite budget constraint",
                    budget_remaining=remaining,
                )

        cost = ModelRouter._estimate_cost(downgraded_model)
        reason = (
            f"Budget constraint (${remaining:.4f} remaining): downgraded from "
            f"{ideal.display_name} [{ideal.tier.value}] → "
            f"{downgraded_model.display_name} [{downgraded_model.tier.value}]"
        )

        return OptimizedDecision(
            model=downgraded_model,
            agent_role=agent_role,
            complexity=complexity,
            estimated_cost_usd=cost,
            was_downgraded=True,
            original_model=ideal,
            reason=reason,
            budget_remaining=remaining,
        )

    def optimize_all_agents(
        self,
        complexity: TaskComplexity,
        agent_roles: Optional[list[str]] = None,
    ) -> dict[str, OptimizedDecision]:
        """Optimize model selection for all agents in a review."""
        from backend.llm.router import _AGENT_TIER
        roles = agent_roles or list(_AGENT_TIER.keys())
        return {
            role: self.optimize_for_agent(role, complexity)
            for role in roles
        }

    def estimate_review_cost(self, complexity: TaskComplexity) -> dict:
        """
        Fast pre-flight estimate: what would this review cost with and without budget constraints?
        No DB writes — purely informational.
        """
        from backend.llm.router import _AGENT_TIER
        router = ModelRouter(preferred_provider=self._preferred_provider)

        full_cost     = 0.0
        optimized_cost = 0.0
        would_downgrade = []
        remaining = self._remaining_budget()

        per_agent = {}
        for role in _AGENT_TIER:
            d = router.route_for_agent(role, complexity)
            full_cost += d.estimated_cost_usd

            if remaining is not None and d.estimated_cost_usd > remaining / len(_AGENT_TIER):
                # Would likely be downgraded
                would_downgrade.append(role)
                # Estimate with fast model
                fast_models = [m for m in _available_models() if m.tier == ModelTier.FAST]
                if fast_models:
                    opt_cost = ModelRouter._estimate_cost(fast_models[0])
                    optimized_cost += opt_cost
                    per_agent[role] = {"ideal": d.model.model_id, "optimized": fast_models[0].model_id, "saving": round(d.estimated_cost_usd - opt_cost, 6)}
                    continue

            optimized_cost += d.estimated_cost_usd
            per_agent[role] = {"ideal": d.model.model_id, "optimized": d.model.model_id, "saving": 0.0}

        return {
            "complexity":            complexity.value,
            "full_cost_usd":         round(full_cost, 6),
            "optimized_cost_usd":    round(optimized_cost, 6),
            "potential_saving_usd":  round(full_cost - optimized_cost, 6),
            "would_downgrade_roles": would_downgrade,
            "budget_remaining":      round(remaining, 4) if remaining is not None else None,
            "per_agent":             per_agent,
        }
