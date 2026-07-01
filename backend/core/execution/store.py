"""
ExecutionStore — CRUD for ExecutionPlan and PlanStep tables.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.execution.schema import ExecutionPlan, PlanStep
from backend.core.execution.parser import ParsedPlan


_EFFORT_ORDER = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5}


def _aggregate_effort(steps: list[PlanStep]) -> str:
    if not steps:
        return "M"
    max_val = max(_EFFORT_ORDER.get(s.effort, 3) for s in steps)
    return {v: k for k, v in _EFFORT_ORDER.items()}.get(max_val, "M")


class ExecutionStore:
    def __init__(self, db_path: str):
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    # ── Plan creation ─────────────────────────────────────────────────────────

    def create_from_parsed(
        self,
        project_path: str,
        parsed: ParsedPlan,
        created_by: Optional[str] = None,
        source: str = "planner",
        source_ref: Optional[str] = None,
        estimated_cost_usd: float = 0.0,
    ) -> ExecutionPlan:
        """Create an ExecutionPlan + all PlanSteps from a ParsedPlan."""
        plan = ExecutionPlan(
            project_path=project_path,
            title=parsed.goal[:200],
            goal=parsed.goal,
            description=parsed.raw,
            source=source,
            source_ref=source_ref,
            status="draft",
            total_steps=len(parsed.steps),
            created_by=created_by,
            estimated_cost_usd=estimated_cost_usd,
        )
        with Session(self._engine) as session:
            session.add(plan)
            session.commit()
            session.refresh(plan)

            db_steps = []
            for ps in parsed.steps:
                step = PlanStep(
                    plan_id=plan.id,
                    step_number=ps.number,
                    title=ps.title,
                    description=ps.description,
                    files=json.dumps(ps.files),
                    effort=ps.effort,
                    agent_type=ps.agent_type,
                    requires_approval=True,
                    status="pending",
                )
                session.add(step)
                db_steps.append(step)

            session.commit()

            # Update aggregate effort
            plan.estimated_effort = _aggregate_effort(db_steps)
            session.add(plan)
            session.commit()
            session.refresh(plan)

        return plan

    def create_manual(
        self,
        project_path: str,
        title: str,
        goal: str,
        steps_data: list[dict],
        created_by: Optional[str] = None,
    ) -> ExecutionPlan:
        """Create a plan from manually specified steps (no parser needed)."""
        plan = ExecutionPlan(
            project_path=project_path,
            title=title,
            goal=goal,
            source="manual",
            status="draft",
            total_steps=len(steps_data),
            created_by=created_by,
        )
        with Session(self._engine) as session:
            session.add(plan)
            session.commit()
            session.refresh(plan)

            for i, sd in enumerate(steps_data, 1):
                step = PlanStep(
                    plan_id=plan.id,
                    step_number=i,
                    title=sd.get("title", f"Step {i}"),
                    description=sd.get("description", ""),
                    files=json.dumps(sd.get("files", [])),
                    effort=sd.get("effort", "M"),
                    agent_type=sd.get("agent_type"),
                    requires_approval=sd.get("requires_approval", True),
                )
                session.add(step)

            session.commit()
            session.refresh(plan)
        return plan

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_plan(self, plan_id: int) -> Optional[ExecutionPlan]:
        with Session(self._engine) as session:
            return session.get(ExecutionPlan, plan_id)

    def get_steps(self, plan_id: int) -> list[PlanStep]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(PlanStep)
                    .where(PlanStep.plan_id == plan_id)
                    .order_by(PlanStep.step_number)  # type: ignore[arg-type]
                )
            )

    def list_plans(
        self, project_path: str, status: Optional[str] = None, limit: int = 50
    ) -> list[ExecutionPlan]:
        with Session(self._engine) as session:
            stmt = (
                select(ExecutionPlan)
                .where(ExecutionPlan.project_path == project_path)
                .order_by(ExecutionPlan.created_at.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            if status:
                stmt = stmt.where(ExecutionPlan.status == status)
            return list(session.exec(stmt))

    # ── Plan lifecycle ────────────────────────────────────────────────────────

    def submit_for_approval(self, plan_id: int) -> Optional[ExecutionPlan]:
        return self._update_plan_status(plan_id, "pending_approval")

    def approve_plan(
        self, plan_id: int, approved_by: str = "human"
    ) -> Optional[ExecutionPlan]:
        with Session(self._engine) as session:
            plan = session.get(ExecutionPlan, plan_id)
            if not plan:
                return None
            plan.status = "approved"
            plan.approved_by = approved_by
            plan.approved_at = datetime.utcnow()
            plan.updated_at = datetime.utcnow()
            # Approve all pending steps — whole-plan sign-off
            steps = list(session.exec(
                select(PlanStep).where(PlanStep.plan_id == plan_id)
            ))
            for step in steps:
                if step.status == "pending":
                    step.status = "approved"
                    step.approved_by = approved_by
                    step.approved_at = datetime.utcnow()
                    session.add(step)
            plan.approved_steps = sum(1 for s in steps if s.status in ("approved", "in_progress", "done"))
            session.add(plan)
            session.commit()
            session.refresh(plan)
            return plan

    def cancel_plan(self, plan_id: int) -> Optional[ExecutionPlan]:
        return self._update_plan_status(plan_id, "cancelled")

    def _update_plan_status(self, plan_id: int, status: str) -> Optional[ExecutionPlan]:
        with Session(self._engine) as session:
            plan = session.get(ExecutionPlan, plan_id)
            if not plan:
                return None
            plan.status = status
            plan.updated_at = datetime.utcnow()
            session.add(plan)
            session.commit()
            session.refresh(plan)
            return plan

    # ── Step lifecycle ────────────────────────────────────────────────────────

    def approve_step(
        self, plan_id: int, step_id: int, approved_by: str = "human"
    ) -> Optional[PlanStep]:
        with Session(self._engine) as session:
            step = self._get_step(session, plan_id, step_id)
            if not step:
                return None
            step.status = "approved"
            step.approved_by = approved_by
            step.approved_at = datetime.utcnow()
            step.updated_at = datetime.utcnow()
            session.add(step)
            session.commit()
            self._refresh_plan_counts(session, plan_id)
            session.refresh(step)
            return step

    def reject_step(
        self, plan_id: int, step_id: int, reason: str = "", approved_by: str = "human"
    ) -> Optional[PlanStep]:
        with Session(self._engine) as session:
            step = self._get_step(session, plan_id, step_id)
            if not step:
                return None
            step.status = "rejected"
            step.rejection_reason = reason
            step.approved_by = approved_by
            step.updated_at = datetime.utcnow()
            session.add(step)
            session.commit()
            session.refresh(step)
            return step

    def start_step(self, plan_id: int, step_id: int) -> Optional[PlanStep]:
        with Session(self._engine) as session:
            step = self._get_step(session, plan_id, step_id)
            if not step or step.status not in ("approved", "pending"):
                return step
            step.status = "in_progress"
            step.started_at = datetime.utcnow()
            step.updated_at = datetime.utcnow()
            session.add(step)
            # Move plan to in_progress if first step starting
            plan = session.get(ExecutionPlan, plan_id)
            if plan and plan.status == "approved":
                plan.status = "in_progress"
                plan.updated_at = datetime.utcnow()
                session.add(plan)
            session.commit()
            session.refresh(step)
            return step

    def complete_step(
        self,
        plan_id: int,
        step_id: int,
        output: str = "",
        output_type: str = "notes",
    ) -> Optional[PlanStep]:
        with Session(self._engine) as session:
            step = self._get_step(session, plan_id, step_id)
            if not step:
                return None
            step.status = "done"
            step.output = output
            step.output_type = output_type
            step.completed_at = datetime.utcnow()
            step.updated_at = datetime.utcnow()
            session.add(step)
            session.commit()
            self._refresh_plan_counts(session, plan_id)
            # Auto-complete plan if all steps done/skipped
            self._maybe_complete_plan(session, plan_id)
            session.refresh(step)
            return step

    def skip_step(self, plan_id: int, step_id: int, reason: str = "") -> Optional[PlanStep]:
        with Session(self._engine) as session:
            step = self._get_step(session, plan_id, step_id)
            if not step:
                return None
            step.status = "skipped"
            step.rejection_reason = reason
            step.updated_at = datetime.utcnow()
            session.add(step)
            session.commit()
            self._refresh_plan_counts(session, plan_id)
            self._maybe_complete_plan(session, plan_id)
            session.refresh(step)
            return step

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _get_step(
        session: Session, plan_id: int, step_id: int
    ) -> Optional[PlanStep]:
        step = session.get(PlanStep, step_id)
        if not step or step.plan_id != plan_id:
            return None
        return step

    def _refresh_plan_counts(self, session: Session, plan_id: int) -> None:
        steps = list(session.exec(
            select(PlanStep).where(PlanStep.plan_id == plan_id)
        ))
        plan = session.get(ExecutionPlan, plan_id)
        if plan:
            plan.approved_steps   = sum(1 for s in steps if s.status in ("approved", "in_progress", "done"))
            plan.completed_steps  = sum(1 for s in steps if s.status in ("done", "skipped"))
            plan.updated_at = datetime.utcnow()
            session.add(plan)
            session.commit()

    def _maybe_complete_plan(self, session: Session, plan_id: int) -> None:
        steps = list(session.exec(
            select(PlanStep).where(PlanStep.plan_id == plan_id)
        ))
        if all(s.status in ("done", "skipped", "rejected") for s in steps):
            plan = session.get(ExecutionPlan, plan_id)
            if plan and plan.status not in ("completed", "cancelled"):
                plan.status = "completed"
                plan.updated_at = datetime.utcnow()
                session.add(plan)
                session.commit()
