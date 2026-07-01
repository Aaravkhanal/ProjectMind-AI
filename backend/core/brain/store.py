"""
BrainStore — CRUD layer for Repository Brain tables.

Backed by the same SQLite file as MemoryStore (they share the DB engine).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.brain.schema import (
    Contributor,
    FileHotspot,
    PRReview,
    ReviewInsight,
    TechDebt,
)


class BrainStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    # ── PRReview ──────────────────────────────────────────────────────────────

    def record_review(
        self,
        project_path: str,
        platform: str = "local",
        pr_number: Optional[int] = None,
        pr_title: Optional[str] = None,
        author: Optional[str] = None,
        base_branch: Optional[str] = None,
        files_changed: int = 0,
        lines_added: int = 0,
        lines_removed: int = 0,
        diff_size_bytes: int = 0,
        task_complexity: str = "medium",
        models_used: Optional[list] = None,
        architect_score: Optional[float] = None,
        security_score: Optional[float] = None,
        quality_score: Optional[float] = None,
        overall_score: Optional[float] = None,
        blocking_issues: int = 0,
        suggestions: int = 0,
        estimated_cost_usd: float = 0.0,
        duration_seconds: Optional[float] = None,
    ) -> PRReview:
        record = PRReview(
            project_path=project_path,
            platform=platform,
            pr_number=pr_number,
            pr_title=pr_title,
            author=author,
            base_branch=base_branch,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            diff_size_bytes=diff_size_bytes,
            task_complexity=task_complexity,
            models_used=json.dumps(models_used or []),
            architect_score=architect_score,
            security_score=security_score,
            quality_score=quality_score,
            overall_score=overall_score,
            blocking_issues=blocking_issues,
            suggestions=suggestions,
            estimated_cost_usd=estimated_cost_usd,
            duration_seconds=duration_seconds,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_reviews(
        self, project_path: str, limit: int = 50
    ) -> list[PRReview]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(PRReview)
                    .where(PRReview.project_path == project_path)
                    .order_by(PRReview.created_at.desc())  # type: ignore[union-attr]
                    .limit(limit)
                )
            )

    # ── FileHotspot ───────────────────────────────────────────────────────────

    def bump_hotspot(
        self,
        project_path: str,
        file_path: str,
        is_bug_fix: bool = False,
        review_flagged: bool = False,
        debt_delta: float = 0.0,
    ) -> FileHotspot:
        with Session(self._engine) as session:
            existing = session.exec(
                select(FileHotspot).where(
                    FileHotspot.project_path == project_path,
                    FileHotspot.file_path == file_path,
                )
            ).first()
            if existing:
                existing.change_count += 1
                if is_bug_fix:
                    existing.bug_count += 1
                if review_flagged:
                    existing.review_flags += 1
                existing.debt_score = min(10.0, existing.debt_score + debt_delta)
                existing.last_changed = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = FileHotspot(
                project_path=project_path,
                file_path=file_path,
                bug_count=1 if is_bug_fix else 0,
                review_flags=1 if review_flagged else 0,
                debt_score=debt_delta,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_hotspots(
        self, project_path: str, limit: int = 20
    ) -> list[FileHotspot]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(FileHotspot)
                    .where(FileHotspot.project_path == project_path)
                    .order_by(FileHotspot.debt_score.desc())  # type: ignore[union-attr]
                    .limit(limit)
                )
            )

    # ── Contributor ───────────────────────────────────────────────────────────

    def update_contributor(
        self,
        project_path: str,
        author: str,
        diff_size: int = 0,
        quality_score: Optional[float] = None,
        security_score: Optional[float] = None,
        blocking_issues: int = 0,
        files: Optional[list[str]] = None,
    ) -> Contributor:
        with Session(self._engine) as session:
            existing = session.exec(
                select(Contributor).where(
                    Contributor.project_path == project_path,
                    Contributor.author == author,
                )
            ).first()
            if existing:
                n = existing.pr_count
                existing.pr_count += 1
                existing.avg_diff_size = (existing.avg_diff_size * n + diff_size) / (n + 1)
                if quality_score is not None:
                    existing.avg_quality_score = (
                        existing.avg_quality_score * n + quality_score
                    ) / (n + 1)
                if security_score is not None:
                    existing.avg_security_score = (
                        existing.avg_security_score * n + security_score
                    ) / (n + 1)
                existing.blocking_issues_total += blocking_issues
                existing.last_pr = datetime.utcnow()
                # Merge file list (keep most frequent, top 5)
                prev = json.loads(existing.most_changed_files or "[]")
                merged = list(dict.fromkeys(prev + (files or [])))[:5]
                existing.most_changed_files = json.dumps(merged)
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = Contributor(
                project_path=project_path,
                author=author,
                pr_count=1,
                avg_diff_size=float(diff_size),
                avg_quality_score=quality_score or 0.0,
                avg_security_score=security_score or 0.0,
                blocking_issues_total=blocking_issues,
                most_changed_files=json.dumps((files or [])[:5]),
                first_pr=datetime.utcnow(),
                last_pr=datetime.utcnow(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_contributors(self, project_path: str) -> list[Contributor]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(Contributor)
                    .where(Contributor.project_path == project_path)
                    .order_by(Contributor.pr_count.desc())  # type: ignore[union-attr]
                )
            )

    # ── TechDebt ──────────────────────────────────────────────────────────────

    def add_debt(
        self,
        project_path: str,
        category: str,
        description: str,
        severity: str = "medium",
        file_path: Optional[str] = None,
        pr_review_id: Optional[int] = None,
    ) -> TechDebt:
        record = TechDebt(
            project_path=project_path,
            category=category,
            description=description,
            severity=severity,
            file_path=file_path,
            pr_review_id=pr_review_id,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_debt(
        self,
        project_path: str,
        resolved: bool = False,
        severity: Optional[str] = None,
    ) -> list[TechDebt]:
        with Session(self._engine) as session:
            stmt = (
                select(TechDebt)
                .where(TechDebt.project_path == project_path)
                .where(TechDebt.resolved == resolved)
            )
            if severity:
                stmt = stmt.where(TechDebt.severity == severity)
            return list(session.exec(stmt.order_by(TechDebt.created_at.desc())))  # type: ignore[arg-type]

    def resolve_debt(self, debt_id: int) -> Optional[TechDebt]:
        with Session(self._engine) as session:
            item = session.get(TechDebt, debt_id)
            if item:
                item.resolved = True
                item.resolved_at = datetime.utcnow()
                session.add(item)
                session.commit()
                session.refresh(item)
            return item

    # ── ReviewInsight ─────────────────────────────────────────────────────────

    def upsert_insight(
        self,
        project_path: str,
        insight_type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        confidence: float = 0.8,
        pr_count_basis: int = 0,
    ) -> ReviewInsight:
        with Session(self._engine) as session:
            existing = session.exec(
                select(ReviewInsight).where(
                    ReviewInsight.project_path == project_path,
                    ReviewInsight.insight_type == insight_type,
                )
            ).first()
            if existing:
                existing.title = title
                existing.body = body
                existing.data_json = json.dumps(data or {})
                existing.confidence = confidence
                existing.pr_count_basis = pr_count_basis
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = ReviewInsight(
                project_path=project_path,
                insight_type=insight_type,
                title=title,
                body=body,
                data_json=json.dumps(data or {}),
                confidence=confidence,
                pr_count_basis=pr_count_basis,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_insights(self, project_path: str) -> list[ReviewInsight]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(ReviewInsight).where(
                        ReviewInsight.project_path == project_path
                    )
                )
            )

    # ── Summary ───────────────────────────────────────────────────────────────

    def get_summary(self, project_path: str) -> dict:
        reviews = self.list_reviews(project_path, limit=100)
        hotspots = self.get_hotspots(project_path, limit=10)
        contributors = self.list_contributors(project_path)
        debt = self.list_debt(project_path, resolved=False)

        avg_score = (
            sum(r.overall_score for r in reviews if r.overall_score) / len(reviews)
            if reviews else 0.0
        )
        total_cost = sum(r.estimated_cost_usd for r in reviews)

        return {
            "total_reviews": len(reviews),
            "avg_overall_score": round(avg_score, 2),
            "total_cost_usd": round(total_cost, 4),
            "open_debt_items": len(debt),
            "critical_debt": sum(1 for d in debt if d.severity == "critical"),
            "top_hotspot_files": [
                {"file": h.file_path, "changes": h.change_count, "debt": h.debt_score}
                for h in hotspots[:5]
            ],
            "contributors": [
                {
                    "author": c.author,
                    "pr_count": c.pr_count,
                    "avg_quality": round(c.avg_quality_score, 2),
                }
                for c in contributors[:5]
            ],
            "complexity_distribution": {
                "simple": sum(1 for r in reviews if r.task_complexity == "simple"),
                "medium": sum(1 for r in reviews if r.task_complexity == "medium"),
                "complex": sum(1 for r in reviews if r.task_complexity == "complex"),
            },
        }
