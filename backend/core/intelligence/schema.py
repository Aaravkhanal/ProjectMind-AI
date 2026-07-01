"""
SQLModel schemas for the Persistent Intelligence Layer (Phase 21).

Tables:
  ArchitecturalDecision — versioned decisions with reasoning and alternatives
  AgentPerformance      — per-run agent telemetry for the self-learning engine
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ArchitecturalDecision(SQLModel, table=True):
    __tablename__ = "architectural_decision"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), index=True
    )
    project_path: str = Field(index=True)
    category: str = Field(default="architecture")
    decision: str
    reasoning: str
    alternatives: str = Field(default="[]")   # JSON list of strings
    models_used: str = Field(default="[]")    # JSON list of model IDs
    confidence: float = Field(default=0.8)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentPerformance(SQLModel, table=True):
    __tablename__ = "agent_performance"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    agent_name: str = Field(index=True)
    task_type: str = Field(default="review")
    success: bool = Field(default=True)
    confidence: float = Field(default=0.0)
    cost_usd: float = Field(default=0.0)
    latency_ms: float = Field(default=0.0)
    tokens_used: int = Field(default=0)
    model_used: str = Field(default="")
    prompt_hash: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
