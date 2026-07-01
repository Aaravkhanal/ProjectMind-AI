"""
Repository Brain — persistent learning tables.

Builds a long-term memory of how a repo evolves:
  - PRReview    : every review produced, with final score
  - FileHotspot : tracks which files change most + accumulate debt
  - Contributor : per-author velocity, churn, quality signals
  - TechDebt    : specific debt items detected during reviews
  - ReviewInsight: aggregated learnings across many reviews
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PRReview(SQLModel, table=True):
    """One record per PR/MR that was reviewed by the system."""

    __tablename__ = "pr_review"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    # Source
    platform: str = Field(default="local")   # "github" | "gitlab" | "local"
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    author: Optional[str] = None
    base_branch: Optional[str] = None

    # Diff stats
    files_changed: int = Field(default=0)
    lines_added: int = Field(default=0)
    lines_removed: int = Field(default=0)
    diff_size_bytes: int = Field(default=0)

    # Routing
    task_complexity: str = Field(default="medium")   # simple | medium | complex
    models_used: str = Field(default="[]")           # JSON list of model IDs

    # Review outputs
    architect_score: Optional[float] = None   # 0–10
    security_score: Optional[float] = None
    quality_score: Optional[float] = None
    overall_score: Optional[float] = None
    blocking_issues: int = Field(default=0)
    suggestions: int = Field(default=0)

    # Cost
    estimated_cost_usd: float = Field(default=0.0)
    duration_seconds: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class FileHotspot(SQLModel, table=True):
    """Tracks how often each file changes and how much debt it carries."""

    __tablename__ = "file_hotspot"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    file_path: str = Field(index=True)

    change_count: int = Field(default=1)
    bug_count: int = Field(default=0)         # times this file was in a bug-fix PR
    review_flags: int = Field(default=0)      # times reviewers flagged this file
    complexity_score: float = Field(default=0.0)
    debt_score: float = Field(default=0.0)    # accumulated from TechDebt records
    last_changed: datetime = Field(default_factory=datetime.utcnow)
    first_seen: datetime = Field(default_factory=datetime.utcnow)


class Contributor(SQLModel, table=True):
    """Per-author statistics derived from reviewed PRs."""

    __tablename__ = "contributor"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    author: str = Field(index=True)

    pr_count: int = Field(default=0)
    avg_diff_size: float = Field(default=0.0)
    avg_quality_score: float = Field(default=0.0)
    avg_security_score: float = Field(default=0.0)
    blocking_issues_total: int = Field(default=0)
    most_changed_files: str = Field(default="[]")   # JSON list of top-5 files
    first_pr: Optional[datetime] = None
    last_pr: Optional[datetime] = None


class TechDebt(SQLModel, table=True):
    """Specific debt items surfaced by the review agents."""

    __tablename__ = "tech_debt"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    file_path: Optional[str] = None
    category: str   # "security" | "architecture" | "quality" | "test_coverage" | "docs"
    severity: str = Field(default="medium")   # "critical" | "high" | "medium" | "low"
    description: str
    pr_review_id: Optional[int] = Field(default=None, foreign_key="pr_review.id")

    resolved: bool = Field(default=False)
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewInsight(SQLModel, table=True):
    """
    Aggregated insights across many reviews — updated by the brain indexer.
    One row per insight type per project.
    """

    __tablename__ = "review_insight"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)

    insight_type: str   # "top_debt_files" | "risky_authors" | "recurring_issues" | "cost_trend"
    title: str
    body: str           # markdown summary
    data_json: str = Field(default="{}")   # supporting data for the insight
    confidence: float = Field(default=0.8)
    pr_count_basis: int = Field(default=0)   # how many PRs this was derived from

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
