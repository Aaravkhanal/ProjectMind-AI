"""
Git Intelligence schema — three tables:

  CommitRecord      — analyzed git commits (type-classified)
  FileChurn         — per-file commit frequency + churn signals
  PRRiskAssessment  — risk score breakdown for a given diff
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class CommitRecord(SQLModel, table=True):
    """One row per analyzed git commit."""

    __tablename__ = "commit_record"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    commit_hash: str = Field(index=True)
    short_hash: str = ""
    author: str = ""
    author_email: str = ""
    commit_date: datetime = Field(default_factory=datetime.utcnow)
    message: str = ""
    commit_type: str = "other"           # feature|bug_fix|refactor|test|docs|chore|revert|other
    is_merge: bool = False

    files_changed: str = Field(default="[]")    # JSON list of file paths
    lines_added: int = Field(default=0)
    lines_removed: int = Field(default=0)
    files_count: int = Field(default=0)

    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class FileChurn(SQLModel, table=True):
    """Per-file churn signals derived from git history."""

    __tablename__ = "file_churn"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    file_path: str = Field(index=True)

    # Rolling windows (commit counts)
    commits_7d: int = Field(default=0)
    commits_30d: int = Field(default=0)
    commits_90d: int = Field(default=0)
    commits_total: int = Field(default=0)

    # Author diversity
    unique_authors: int = Field(default=0)
    authors_json: str = Field(default="[]")      # JSON list of author names

    # Quality signals
    bug_fix_commits: int = Field(default=0)       # commits touching this file that were bug-fixes
    revert_commits: int = Field(default=0)

    # Temporal signals
    first_commit: Optional[datetime] = None
    last_commit: Optional[datetime] = None
    avg_days_between_commits: float = Field(default=0.0)

    # Derived score (0–10, higher = more churny/risky)
    churn_score: float = Field(default=0.0)

    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PRRiskAssessment(SQLModel, table=True):
    """Risk score for a diff/PR, with per-factor breakdown."""

    __tablename__ = "pr_risk_assessment"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    # Source reference
    diff_hash: str = ""                  # md5 of diff text (dedup key)
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    author: Optional[str] = None

    # Overall
    overall_risk: float = Field(default=0.0)     # 0–10
    risk_level: str = Field(default="low")       # low|medium|high|critical

    # Per-factor scores (0–10 each)
    size_risk: float = Field(default=0.0)
    churn_risk: float = Field(default=0.0)
    critical_file_risk: float = Field(default=0.0)
    test_coverage_risk: float = Field(default=0.0)
    author_risk: float = Field(default=0.0)
    complexity_risk: float = Field(default=0.0)

    # Supporting data
    files_changed: str = Field(default="[]")
    critical_files: str = Field(default="[]")    # files matching critical patterns
    missing_tests: bool = Field(default=False)
    breakdown_json: str = Field(default="{}")    # full explanation per factor

    created_at: datetime = Field(default_factory=datetime.utcnow)
