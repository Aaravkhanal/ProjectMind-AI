"""
GitIntelStore — persists and retrieves Git Intelligence data.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.git_intel.schema import CommitRecord, FileChurn, PRRiskAssessment
from backend.core.git_intel.analyzer import CommitData, ChurnData
from backend.core.git_intel.risk import RiskResult


class GitIntelStore:
    def __init__(self, db_path: str):
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    # ── Commits ────────────────────────────────────────────────────────────────

    def upsert_commits(
        self, project_path: str, commits: list[CommitData]
    ) -> int:
        """Insert commits that aren't already stored. Returns count inserted."""
        inserted = 0
        with Session(self._engine) as session:
            existing = set(
                row
                for row in session.exec(
                    select(CommitRecord.commit_hash).where(
                        CommitRecord.project_path == project_path
                    )
                )
            )
            for c in commits:
                if c.commit_hash in existing:
                    continue
                record = CommitRecord(
                    project_path=project_path,
                    commit_hash=c.commit_hash,
                    short_hash=c.short_hash,
                    author=c.author,
                    author_email=c.author_email,
                    commit_date=c.commit_date.replace(tzinfo=None),
                    message=c.message[:500],
                    commit_type=c.commit_type,
                    is_merge=c.is_merge,
                    files_changed=json.dumps(c.files[:50]),
                    lines_added=c.lines_added,
                    lines_removed=c.lines_removed,
                    files_count=len(c.files),
                )
                session.add(record)
                inserted += 1
            session.commit()
        return inserted

    def list_commits(
        self,
        project_path: str,
        commit_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[CommitRecord]:
        with Session(self._engine) as session:
            stmt = (
                select(CommitRecord)
                .where(CommitRecord.project_path == project_path)
                .order_by(CommitRecord.commit_date.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            if commit_type:
                stmt = stmt.where(CommitRecord.commit_type == commit_type)
            return list(session.exec(stmt))

    def commit_type_distribution(self, project_path: str) -> dict[str, int]:
        commits = self.list_commits(project_path, limit=500)
        dist: dict[str, int] = {}
        for c in commits:
            dist[c.commit_type] = dist.get(c.commit_type, 0) + 1
        return dist

    # ── File churn ─────────────────────────────────────────────────────────────

    def upsert_churn(
        self, project_path: str, churn_map: dict[str, ChurnData]
    ) -> int:
        upserted = 0
        with Session(self._engine) as session:
            for fp, cd in churn_map.items():
                existing = session.exec(
                    select(FileChurn).where(
                        FileChurn.project_path == project_path,
                        FileChurn.file_path == fp,
                    )
                ).first()

                if existing:
                    existing.commits_7d  = cd.commits_7d
                    existing.commits_30d = cd.commits_30d
                    existing.commits_90d = cd.commits_90d
                    existing.commits_total = cd.commits_total
                    existing.unique_authors = len(cd.unique_authors)
                    existing.authors_json   = json.dumps(cd.unique_authors[:20])
                    existing.bug_fix_commits  = cd.bug_fix_commits
                    existing.revert_commits   = cd.revert_commits
                    existing.avg_days_between_commits = cd.avg_days_between_commits
                    existing.churn_score = cd.churn_score
                    existing.updated_at  = datetime.utcnow()
                    session.add(existing)
                else:
                    record = FileChurn(
                        project_path=project_path,
                        file_path=fp,
                        commits_7d=cd.commits_7d,
                        commits_30d=cd.commits_30d,
                        commits_90d=cd.commits_90d,
                        commits_total=cd.commits_total,
                        unique_authors=len(cd.unique_authors),
                        authors_json=json.dumps(cd.unique_authors[:20]),
                        bug_fix_commits=cd.bug_fix_commits,
                        revert_commits=cd.revert_commits,
                        first_commit=cd.first_commit.replace(tzinfo=None) if cd.first_commit else None,
                        last_commit=cd.last_commit.replace(tzinfo=None) if cd.last_commit else None,
                        avg_days_between_commits=cd.avg_days_between_commits,
                        churn_score=cd.churn_score,
                    )
                    session.add(record)
                upserted += 1
            session.commit()
        return upserted

    def get_churn(self, project_path: str, file_path: str) -> Optional[FileChurn]:
        with Session(self._engine) as session:
            return session.exec(
                select(FileChurn).where(
                    FileChurn.project_path == project_path,
                    FileChurn.file_path == file_path,
                )
            ).first()

    def top_churn_files(
        self, project_path: str, limit: int = 20
    ) -> list[FileChurn]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(FileChurn)
                    .where(FileChurn.project_path == project_path)
                    .order_by(FileChurn.churn_score.desc())  # type: ignore[union-attr]
                    .limit(limit)
                )
            )

    # ── Risk assessments ───────────────────────────────────────────────────────

    def save_risk(
        self,
        project_path: str,
        result: RiskResult,
        pr_number: Optional[int] = None,
        pr_title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PRRiskAssessment:
        record = PRRiskAssessment(
            project_path=project_path,
            diff_hash=result.diff_hash,
            pr_number=pr_number,
            pr_title=pr_title,
            author=author,
            overall_risk=result.overall_risk,
            risk_level=result.risk_level,
            size_risk=next((b.score for b in result.breakdown if b.factor == "size"), 0.0),
            churn_risk=next((b.score for b in result.breakdown if b.factor == "churn"), 0.0),
            critical_file_risk=next((b.score for b in result.breakdown if b.factor == "critical_file"), 0.0),
            test_coverage_risk=next((b.score for b in result.breakdown if b.factor == "test_coverage"), 0.0),
            author_risk=next((b.score for b in result.breakdown if b.factor == "author"), 0.0),
            complexity_risk=next((b.score for b in result.breakdown if b.factor == "complexity"), 0.0),
            files_changed=json.dumps(result.files_changed),
            critical_files=json.dumps(result.critical_files),
            missing_tests=result.missing_tests,
            breakdown_json=json.dumps([
                {
                    "factor": b.factor,
                    "score": b.score,
                    "weight": b.weight,
                    "explanation": b.explanation,
                    "evidence": b.evidence,
                }
                for b in result.breakdown
            ]),
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_risk_assessments(
        self, project_path: str, limit: int = 50
    ) -> list[PRRiskAssessment]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(PRRiskAssessment)
                    .where(PRRiskAssessment.project_path == project_path)
                    .order_by(PRRiskAssessment.created_at.desc())  # type: ignore[union-attr]
                    .limit(limit)
                )
            )

    # ── Summary ────────────────────────────────────────────────────────────────

    def get_intel_summary(self, project_path: str) -> dict:
        commits = self.list_commits(project_path, limit=500)
        churn   = self.top_churn_files(project_path, limit=10)
        risks   = self.list_risk_assessments(project_path, limit=20)
        dist    = self.commit_type_distribution(project_path)

        return {
            "total_commits_analyzed": len(commits),
            "commit_type_distribution": dist,
            "top_churn_files": [
                {
                    "file": f.file_path,
                    "commits_30d": f.commits_30d,
                    "bug_fixes": f.bug_fix_commits,
                    "churn_score": f.churn_score,
                }
                for f in churn[:5]
            ],
            "recent_risk_assessments": [
                {
                    "pr_number": r.pr_number,
                    "pr_title": r.pr_title,
                    "risk_level": r.risk_level,
                    "overall_risk": r.overall_risk,
                    "created_at": r.created_at.isoformat(),
                }
                for r in risks[:5]
            ],
            "high_risk_prs": sum(1 for r in risks if r.risk_level in ("high", "critical")),
        }
