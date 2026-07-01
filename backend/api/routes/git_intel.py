"""
Git Intelligence API.

POST /git-intel/analyze              — index a repo's git history into the DB
GET  /git-intel/summary              — dashboard: commit types, churn, risk trends
GET  /git-intel/commits              — recent commits with type classification
GET  /git-intel/churn                — per-file churn scores (highest first)
GET  /git-intel/co-changes           — files that always change with a given file
POST /git-intel/score-risk           — score a diff/PR for risk (0–10, with breakdown)
GET  /git-intel/risk-history         — past risk assessments for a project
POST /git-intel/classify-commit      — classify a commit message (no git repo needed)
"""

from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/git-intel", tags=["git-intelligence"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _store():
    from backend.core.git_intel.store import GitIntelStore
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    s = GitIntelStore(db_path=db_path)
    s.init_db()
    return s


# ── request / response models ──────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    project_path: str = "."
    max_commits: int = 200
    since_days: Optional[int] = None   # e.g. 90 for last 3 months only


class RiskScoreRequest(BaseModel):
    diff: str
    project_path: str = "."
    author: Optional[str] = None
    pr_number: Optional[int] = None
    pr_title: str = ""
    use_churn_data: bool = True        # load churn from DB to enrich the score
    use_brain_data: bool = True        # load author quality from brain DB


class ClassifyRequest(BaseModel):
    messages: list[str]               # 1..N commit messages to classify


# ── routes ─────────────────────────────────────────────────────────────────────

@router.post("/analyze", summary="Index a repo's git history")
def analyze_repo(req: AnalyzeRequest):
    """
    Runs git log on the given project path, classifies each commit,
    computes file churn scores, and persists everything to the DB.

    Safe to call repeatedly — already-seen commits are skipped (upsert).
    """
    from backend.core.git_intel.analyzer import analyze_history, analyze_file_churn

    if not os.path.isdir(req.project_path):
        raise HTTPException(400, f"Directory not found: {req.project_path}")

    commits = analyze_history(
        req.project_path,
        max_commits=req.max_commits,
        since_days=req.since_days,
    )
    if not commits:
        raise HTTPException(422, "No commits found — is this a git repository?")

    churn_map = analyze_file_churn(req.project_path, commits=commits)

    store = _store()
    inserted_commits = store.upsert_commits(req.project_path, commits)
    upserted_churn   = store.upsert_churn(req.project_path, churn_map)

    from backend.core.git_intel.classifier import type_distribution
    dist = type_distribution([c.message for c in commits])

    return {
        "commits_found":    len(commits),
        "commits_inserted": inserted_commits,
        "files_indexed":    upserted_churn,
        "type_distribution": dist,
        "top_authors": _top_authors(commits),
    }


@router.get("/summary", summary="Git intelligence dashboard")
def get_summary(project_path: str = "."):
    store = _store()
    return store.get_intel_summary(project_path)


@router.get("/commits", summary="Recent commits with type classification")
def get_commits(
    project_path: str = ".",
    commit_type: Optional[str] = None,
    limit: int = 50,
):
    store = _store()
    commits = store.list_commits(project_path, commit_type=commit_type, limit=limit)
    return [
        {
            "hash":         c.short_hash,
            "author":       c.author,
            "date":         c.commit_date.isoformat(),
            "message":      c.message,
            "type":         c.commit_type,
            "files":        json.loads(c.files_changed or "[]"),
            "lines_added":  c.lines_added,
            "lines_removed": c.lines_removed,
        }
        for c in commits
    ]


@router.get("/churn", summary="Files ranked by churn score (highest risk first)")
def get_churn(project_path: str = ".", limit: int = 30):
    store = _store()
    files = store.top_churn_files(project_path, limit=limit)
    return [
        {
            "file_path":          f.file_path,
            "churn_score":        f.churn_score,
            "commits_7d":         f.commits_7d,
            "commits_30d":        f.commits_30d,
            "commits_90d":        f.commits_90d,
            "commits_total":      f.commits_total,
            "unique_authors":     f.unique_authors,
            "bug_fix_commits":    f.bug_fix_commits,
            "revert_commits":     f.revert_commits,
            "avg_days_between":   f.avg_days_between_commits,
            "last_commit":        f.last_commit.isoformat() if f.last_commit else None,
        }
        for f in files
    ]


@router.get("/co-changes", summary="Files that frequently change together with a target file")
def get_co_changes(
    file_path: str,
    project_path: str = ".",
    top_n: int = 10,
):
    """
    Useful for understanding blast radius: if you touch file_path,
    which other files are likely to need changes too?
    """
    from backend.core.git_intel.analyzer import analyze_history, co_changed_files

    if not os.path.isdir(project_path):
        raise HTTPException(400, f"Directory not found: {project_path}")

    commits = analyze_history(project_path, max_commits=300)
    pairs = co_changed_files(project_path, file_path, commits=commits, top_n=top_n)

    return {
        "target_file": file_path,
        "co_changed": [
            {"file": fp, "co_change_count": count}
            for fp, count in pairs
        ],
    }


@router.post("/score-risk", summary="Score a diff for risk (0–10) with breakdown")
def score_risk(req: RiskScoreRequest):
    """
    Six-factor risk score for a diff:
      size · churn · critical_files · test_coverage · author · complexity

    Optionally enriches with churn data from DB and author quality from brain DB.
    """
    from backend.core.git_intel.risk import PRRiskScorer
    from backend.core.git_intel.analyzer import ChurnData

    churn_data: dict[str, ChurnData] = {}
    if req.use_churn_data:
        from backend.core.git_intel.analyzer import parse_diff_files
        store = _store()
        files = parse_diff_files(req.diff)
        for fp in files:
            row = store.get_churn(req.project_path, fp)
            if row:
                churn_data[fp] = ChurnData(
                    file_path=fp,
                    commits_7d=row.commits_7d,
                    commits_30d=row.commits_30d,
                    commits_90d=row.commits_90d,
                    commits_total=row.commits_total,
                    unique_authors=json.loads(row.authors_json or "[]"),
                    bug_fix_commits=row.bug_fix_commits,
                    revert_commits=row.revert_commits,
                    first_commit=row.first_commit,
                    last_commit=row.last_commit,
                    avg_days_between_commits=row.avg_days_between_commits,
                    churn_score=row.churn_score,
                )

    # Pull author quality score from brain DB if available
    author_quality: Optional[float] = None
    if req.use_brain_data and req.author:
        try:
            from backend.core.brain.store import BrainStore
            brain = BrainStore(db_path=os.environ.get("DB_PATH", ".projectmind/memory.db"))
            brain.init_db()
            contributors = brain.list_contributors(req.project_path)
            for c in contributors:
                if c.author == req.author:
                    author_quality = c.avg_quality_score
                    break
        except Exception:
            pass

    scorer  = PRRiskScorer()
    result  = scorer.score(
        diff=req.diff,
        project_path=req.project_path,
        author=req.author,
        pr_title=req.pr_title,
        churn_data=churn_data or None,
        author_quality_score=author_quality,
    )

    # Persist the assessment
    store = _store()
    store.save_risk(
        project_path=req.project_path,
        result=result,
        pr_number=req.pr_number,
        pr_title=req.pr_title or None,
        author=req.author,
    )

    return {
        "overall_risk":    result.overall_risk,
        "risk_level":      result.risk_level,
        "summary":         result.summary,
        "files_changed":   result.files_changed,
        "critical_files":  result.critical_files,
        "missing_tests":   result.missing_tests,
        "breakdown": [
            {
                "factor":      b.factor,
                "score":       b.score,
                "weight":      b.weight,
                "explanation": b.explanation,
                "evidence":    b.evidence,
            }
            for b in result.breakdown
        ],
    }


@router.get("/risk-history", summary="Past risk assessments for a project")
def get_risk_history(project_path: str = ".", limit: int = 50):
    store = _store()
    risks = store.list_risk_assessments(project_path, limit=limit)
    return [
        {
            "id":             r.id,
            "pr_number":      r.pr_number,
            "pr_title":       r.pr_title,
            "author":         r.author,
            "risk_level":     r.risk_level,
            "overall_risk":   r.overall_risk,
            "critical_files": json.loads(r.critical_files or "[]"),
            "missing_tests":  r.missing_tests,
            "created_at":     r.created_at.isoformat(),
        }
        for r in risks
    ]


@router.post("/classify-commit", summary="Classify commit messages by type")
def classify_commits(req: ClassifyRequest):
    """
    Classify one or more commit messages without needing a git repo.
    Useful for CI pipelines or commit hooks.
    """
    from backend.core.git_intel.classifier import classify, type_distribution

    results = [
        {"message": msg, "type": classify(msg)}
        for msg in req.messages
    ]
    return {
        "results":      results,
        "distribution": type_distribution(req.messages),
    }


# ── internal helpers ───────────────────────────────────────────────────────────

def _top_authors(commits) -> list[dict]:
    counts: dict[str, int] = {}
    for c in commits:
        counts[c.author] = counts.get(c.author, 0) + 1
    return [
        {"author": a, "commits": n}
        for a, n in sorted(counts.items(), key=lambda x: -x[1])[:5]
    ]
