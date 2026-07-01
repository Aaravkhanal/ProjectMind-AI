"""
CostStore — CRUD + analytics for the Cost Optimization Engine.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.cost.schema import CostAlert, CostBudget, CostRecord


def _billing_month(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.utcnow()
    return d.strftime("%Y-%m")


class CostStore:
    def __init__(self, db_path: str):
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    # ── Budget ─────────────────────────────────────────────────────────────────

    def set_budget(
        self,
        project_path: str,
        monthly_limit_usd: float = 10.0,
        alert_at_percent: float = 80.0,
        hard_limit: bool = False,
        fallback_tier: str = "fast",
    ) -> CostBudget:
        with Session(self._engine) as session:
            existing = session.exec(
                select(CostBudget).where(CostBudget.project_path == project_path)
            ).first()
            if existing:
                existing.monthly_limit_usd = monthly_limit_usd
                existing.alert_at_percent  = alert_at_percent
                existing.hard_limit        = hard_limit
                existing.fallback_tier     = fallback_tier
                existing.updated_at        = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = CostBudget(
                project_path=project_path,
                monthly_limit_usd=monthly_limit_usd,
                alert_at_percent=alert_at_percent,
                hard_limit=hard_limit,
                fallback_tier=fallback_tier,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_budget(self, project_path: str) -> Optional[CostBudget]:
        with Session(self._engine) as session:
            return session.exec(
                select(CostBudget).where(CostBudget.project_path == project_path)
            ).first()

    # ── Cost recording ─────────────────────────────────────────────────────────

    def record_cost(
        self,
        project_path: str,
        operation: str,
        model_id: str,
        provider: str,
        model_tier: str = "balanced",
        agent_role: Optional[str] = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        estimated_cost_usd: float = 0.0,
        actual_cost_usd: float = 0.0,
        cost_source: str = "estimated",
        was_downgraded: bool = False,
        original_model_id: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> CostRecord:
        record = CostRecord(
            project_path=project_path,
            operation=operation,
            agent_role=agent_role,
            provider=provider,
            model_id=model_id,
            model_tier=model_tier,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_total=tokens_input + tokens_output,
            estimated_cost_usd=estimated_cost_usd,
            actual_cost_usd=actual_cost_usd or estimated_cost_usd,
            cost_source=cost_source,
            was_downgraded=was_downgraded,
            original_model_id=original_model_id,
            duration_seconds=duration_seconds,
            billing_month=_billing_month(),
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        # Fire budget alerts if needed
        self._check_and_alert(project_path)
        return record

    def get_spend(
        self,
        project_path: str,
        billing_month: Optional[str] = None,
    ) -> float:
        month = billing_month or _billing_month()
        with Session(self._engine) as session:
            records = list(session.exec(
                select(CostRecord).where(
                    CostRecord.project_path == project_path,
                    CostRecord.billing_month == month,
                )
            ))
        return sum(r.actual_cost_usd for r in records)

    def list_records(
        self,
        project_path: str,
        billing_month: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> list[CostRecord]:
        with Session(self._engine) as session:
            stmt = (
                select(CostRecord)
                .where(CostRecord.project_path == project_path)
                .order_by(CostRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            if billing_month:
                stmt = stmt.where(CostRecord.billing_month == billing_month)
            if operation:
                stmt = stmt.where(CostRecord.operation == operation)
            return list(session.exec(stmt))

    # ── Alerts ─────────────────────────────────────────────────────────────────

    def list_alerts(
        self, project_path: str, unacknowledged_only: bool = False
    ) -> list[CostAlert]:
        with Session(self._engine) as session:
            stmt = select(CostAlert).where(
                CostAlert.project_path == project_path
            ).order_by(CostAlert.created_at.desc())  # type: ignore[union-attr]
            if unacknowledged_only:
                stmt = stmt.where(CostAlert.acknowledged == False)  # noqa: E712
            return list(session.exec(stmt))

    def acknowledge_alerts(self, project_path: str) -> int:
        with Session(self._engine) as session:
            alerts = list(session.exec(
                select(CostAlert).where(
                    CostAlert.project_path == project_path,
                    CostAlert.acknowledged == False,  # noqa: E712
                )
            ))
            for a in alerts:
                a.acknowledged = True
                session.add(a)
            session.commit()
            return len(alerts)

    def _check_and_alert(self, project_path: str) -> None:
        budget = self.get_budget(project_path)
        if not budget:
            return

        spend = self.get_spend(project_path)
        pct   = (spend / budget.monthly_limit_usd * 100) if budget.monthly_limit_usd else 0

        thresholds = [
            (budget.alert_at_percent,      f"threshold_{int(budget.alert_at_percent)}"),
            (100.0,                         "threshold_100"),
        ]
        with Session(self._engine) as session:
            month = _billing_month()
            for threshold_pct, alert_type in thresholds:
                if pct >= threshold_pct:
                    already = session.exec(
                        select(CostAlert).where(
                            CostAlert.project_path == project_path,
                            CostAlert.alert_type == alert_type,
                            CostAlert.created_at >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0),
                        )
                    ).first()
                    if not already:
                        alert = CostAlert(
                            project_path=project_path,
                            alert_type=alert_type,
                            message=(
                                f"Budget {threshold_pct:.0f}% used: "
                                f"${spend:.4f} of ${budget.monthly_limit_usd:.2f} "
                                f"({pct:.1f}%)"
                            ),
                            spend_at_alert=spend,
                            budget_limit=budget.monthly_limit_usd,
                            percent_used=pct,
                        )
                        session.add(alert)
                        session.commit()

    # ── Analytics ──────────────────────────────────────────────────────────────

    def get_summary(self, project_path: str) -> dict:
        month     = _billing_month()
        prev_month = _billing_month(datetime.utcnow().replace(day=1) - timedelta(days=1))

        records_this  = self.list_records(project_path, billing_month=month, limit=500)
        records_prev  = self.list_records(project_path, billing_month=prev_month, limit=500)
        budget        = self.get_budget(project_path)
        alerts        = self.list_alerts(project_path, unacknowledged_only=True)

        spend_this = sum(r.actual_cost_usd for r in records_this)
        spend_prev = sum(r.actual_cost_usd for r in records_prev)

        # Per-operation breakdown
        by_op: dict[str, float] = {}
        by_tier: dict[str, float] = {}
        by_model: dict[str, float] = {}
        downgraded = 0

        for r in records_this:
            by_op[r.operation]     = by_op.get(r.operation, 0) + r.actual_cost_usd
            by_tier[r.model_tier]  = by_tier.get(r.model_tier, 0) + r.actual_cost_usd
            by_model[r.model_id]   = by_model.get(r.model_id, 0) + r.actual_cost_usd
            if r.was_downgraded:
                downgraded += 1

        # Forecast: linear projection from days elapsed
        day_of_month = datetime.utcnow().day
        days_in_month = 30
        monthly_forecast = (spend_this / day_of_month * days_in_month) if day_of_month > 0 else 0

        return {
            "billing_month":         month,
            "spend_this_month":      round(spend_this, 6),
            "spend_last_month":      round(spend_prev, 6),
            "monthly_forecast_usd":  round(monthly_forecast, 4),
            "budget": {
                "limit":           budget.monthly_limit_usd if budget else None,
                "alert_at":        budget.alert_at_percent if budget else None,
                "hard_limit":      budget.hard_limit if budget else False,
                "percent_used":    round(spend_this / budget.monthly_limit_usd * 100, 1) if budget and budget.monthly_limit_usd else None,
                "remaining":       round((budget.monthly_limit_usd - spend_this), 4) if budget else None,
            },
            "breakdown_by_operation": dict(sorted(by_op.items(), key=lambda x: -x[1])),
            "breakdown_by_tier":      dict(sorted(by_tier.items(), key=lambda x: -x[1])),
            "top_models_by_cost":     dict(sorted(by_model.items(), key=lambda x: -x[1])[:5]),
            "total_operations":       len(records_this),
            "downgraded_count":       downgraded,
            "unacknowledged_alerts":  len(alerts),
            "mom_change_pct":         round((spend_this - spend_prev) / spend_prev * 100, 1) if spend_prev else None,
        }
