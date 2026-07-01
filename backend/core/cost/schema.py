"""
Cost Optimization Engine schema — three tables:

  CostBudget   — per-project monthly budget + alert thresholds
  CostRecord   — actual cost of each AI operation (model + tokens used)
  CostAlert    — triggered events when spend crosses a threshold
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class CostBudget(SQLModel, table=True):
    __tablename__ = "cost_budget"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True, unique=True)

    monthly_limit_usd: float = Field(default=10.0)
    alert_at_percent: float = Field(default=80.0)   # fire alert at 80% of limit
    hard_limit: bool = Field(default=False)          # if True, block calls when limit hit

    # Preferred cost tier when budget is tight
    fallback_tier: str = Field(default="fast")       # fast|balanced|powerful|reasoning

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CostRecord(SQLModel, table=True):
    __tablename__ = "cost_record"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    operation: str            # "review" | "plan" | "refactor" | "testing" | "docs" | "pipeline"
    agent_role: Optional[str] = None    # "architect" | "security" | "quality" | etc.

    provider: str = ""
    model_id: str = ""
    model_tier: str = ""      # fast|balanced|powerful|reasoning

    # Token counts (actual, if available; estimated otherwise)
    tokens_input: int = Field(default=0)
    tokens_output: int = Field(default=0)
    tokens_total: int = Field(default=0)

    # Costs
    estimated_cost_usd: float = Field(default=0.0)
    actual_cost_usd: float = Field(default=0.0)
    cost_source: str = Field(default="estimated")   # "estimated" | "actual"

    # Whether the optimizer downgraded the model
    was_downgraded: bool = Field(default=False)
    original_model_id: Optional[str] = None        # model that would have been used without budget constraint

    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Rolling period for budget accounting (YYYY-MM)
    billing_month: str = Field(default="")


class CostAlert(SQLModel, table=True):
    __tablename__ = "cost_alert"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    alert_type: str    # "threshold_80" | "threshold_100" | "hard_limit_hit" | "forecast_overrun"
    message: str
    spend_at_alert: float
    budget_limit: float
    percent_used: float

    acknowledged: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
