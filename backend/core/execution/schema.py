"""
Execution Planning schema — two tables:

  ExecutionPlan  — the overall plan (title, goal, status, created_by)
  PlanStep       — individual steps within a plan (ordered, approvable)

Status flow:
  Plan:  draft → pending_approval → approved → in_progress → completed | cancelled
  Step:  pending → approved | rejected → in_progress → done | skipped
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ExecutionPlan(SQLModel, table=True):
    __tablename__ = "execution_plan"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    title: str
    goal: str                                 # one-sentence goal from planner
    description: str = ""                     # full planner markdown output
    source: str = Field(default="planner")    # "planner" | "manual" | "review"
    source_ref: Optional[str] = None          # e.g. PR number or task id

    status: str = Field(default="draft")      # draft|pending_approval|approved|in_progress|completed|cancelled
    total_steps: int = Field(default=0)
    approved_steps: int = Field(default=0)
    completed_steps: int = Field(default=0)

    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    estimated_effort: Optional[str] = None    # XS | S | M | L | XL (aggregate)
    estimated_cost_usd: float = Field(default=0.0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStep(SQLModel, table=True):
    __tablename__ = "plan_step"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="execution_plan.id", index=True)

    step_number: int
    title: str
    description: str = ""
    files: str = Field(default="[]")           # JSON list of file paths
    effort: str = Field(default="M")           # XS | S | M | L | XL

    # What kind of agent to use when executing this step
    agent_type: Optional[str] = None           # "planner"|"refactor"|"testing"|"docs"|None

    requires_approval: bool = Field(default=True)
    status: str = Field(default="pending")     # pending|approved|rejected|in_progress|done|skipped

    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Output from executing the step (agent output or human notes)
    output: Optional[str] = None
    output_type: Optional[str] = None          # "code" | "markdown" | "notes"

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
