"""
Phase 21 — Decision Store.

Persists architectural, security, dependency, and deployment decisions with
full reasoning chains, alternatives considered, and model attribution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.intelligence.schema import ArchitecturalDecision


class DecisionStore:
    def __init__(self, brain_dir: Path):
        db_path = brain_dir / "decisions.db"
        brain_dir.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self._engine)

    # ── write ──────────────────────────────────────────────────────────────────

    def record(
        self,
        project_path: str,
        decision: str,
        reasoning: str,
        alternatives: Optional[list[str]] = None,
        models_used: Optional[list[str]] = None,
        confidence: float = 0.8,
        category: str = "architecture",
    ) -> ArchitecturalDecision:
        record = ArchitecturalDecision(
            project_path=project_path,
            category=category,
            decision=decision,
            reasoning=reasoning,
            alternatives=json.dumps(alternatives or []),
            models_used=json.dumps(models_used or []),
            confidence=confidence,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    # ── read ───────────────────────────────────────────────────────────────────

    def list(
        self,
        project_path: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[ArchitecturalDecision]:
        with Session(self._engine) as session:
            stmt = select(ArchitecturalDecision).where(
                ArchitecturalDecision.project_path == project_path
            )
            if category:
                stmt = stmt.where(ArchitecturalDecision.category == category)
            stmt = stmt.order_by(
                ArchitecturalDecision.created_at.desc()  # type: ignore[union-attr]
            ).limit(limit)
            return list(session.exec(stmt))

    def get(self, decision_id: str) -> Optional[ArchitecturalDecision]:
        with Session(self._engine) as session:
            return session.exec(
                select(ArchitecturalDecision).where(
                    ArchitecturalDecision.decision_id == decision_id
                )
            ).first()

    def serialize(self, d: ArchitecturalDecision) -> dict:
        return {
            "decision_id": d.decision_id,
            "category": d.category,
            "decision": d.decision,
            "reasoning": d.reasoning,
            "alternatives": json.loads(d.alternatives),
            "models_used": json.loads(d.models_used),
            "confidence": d.confidence,
            "timestamp": d.created_at.isoformat(),
        }
