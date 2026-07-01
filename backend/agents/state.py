from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class ReviewState(TypedDict):
    # ── inputs ────────────────────────────────────────────────────────────────
    diff: str
    pr_info: dict
    project_context: str        # compressed context from SmartPromptGenerator
    llm_provider: str
    api_key: str
    model_name: str             # legacy single-model fallback

    # ── multi-model routing (all optional — router fills in defaults) ─────────
    task_complexity: str        # "simple" | "medium" | "complex"; auto-detected if blank
    budget_per_task_usd: float  # router won't pick models that exceed this per review
    agent_model_overrides: dict # {"security": {"provider": "nvidia", "model_id": "..."}}

    # ── specialist outputs (written by parallel nodes) ────────────────────────
    architect_review: str
    security_review: str
    quality_review: str

    # ── synthesized output ────────────────────────────────────────────────────
    final_review: str

    # ── errors from any node (merged across parallel branches) ────────────────
    errors: Annotated[list[str], operator.add]
