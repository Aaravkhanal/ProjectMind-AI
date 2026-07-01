"""
GitAnalyzer — extracts intelligence from a local git repository.

All operations use subprocess git commands (no external git library).
Results are returned as plain dicts/dataclasses, ready to persist via GitIntelStore.

Key methods:
  analyze_history(project_path, max_commits)  → list of CommitData
  analyze_file_churn(project_path)            → dict[file_path, ChurnData]
  get_recent_authors(project_path, days)      → list of AuthorData
  co_changed_files(project_path, file_path)   → list of (file, frequency)
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.core.git_intel.classifier import classify


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CommitData:
    commit_hash: str
    short_hash: str
    author: str
    author_email: str
    commit_date: datetime
    message: str
    commit_type: str
    is_merge: bool
    files: list[str]
    lines_added: int
    lines_removed: int


@dataclass
class ChurnData:
    file_path: str
    commits_7d: int
    commits_30d: int
    commits_90d: int
    commits_total: int
    unique_authors: list[str]
    bug_fix_commits: int
    revert_commits: int
    first_commit: Optional[datetime]
    last_commit: Optional[datetime]
    avg_days_between_commits: float
    churn_score: float


@dataclass
class AuthorData:
    name: str
    email: str
    commit_count: int
    bug_fix_count: int
    lines_added: int
    lines_removed: int
    active_files: list[str]
    first_commit: Optional[datetime]
    last_commit: Optional[datetime]


# ── Subprocess helper ──────────────────────────────────────────────────────────

def _git(project_path: str, *args: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _is_git_repo(project_path: str) -> bool:
    return bool(_git(project_path, "rev-parse", "--git-dir"))


# ── Commit history ─────────────────────────────────────────────────────────────

_LOG_FORMAT = "%H\x1f%h\x1f%an\x1f%ae\x1f%ai\x1f%s\x1f%P"
_FIELD_SEP   = "\x1f"
_RECORD_SEP  = "\x1e"


def analyze_history(
    project_path: str,
    max_commits: int = 200,
    since_days: Optional[int] = None,
) -> list[CommitData]:
    """
    Parse recent commit history into CommitData records.
    Uses a low-overhead format string — no per-commit subprocess calls.
    """
    if not _is_git_repo(project_path):
        return []

    args = ["log", f"--format={_LOG_FORMAT}{_RECORD_SEP}", f"-{max_commits}"]
    if since_days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
        args.append(f"--since={cutoff}")

    raw = _git(project_path, *args, timeout=30)
    records = [r.strip() for r in raw.split(_RECORD_SEP) if r.strip()]

    commits: list[CommitData] = []
    for rec in records:
        fields = rec.split(_FIELD_SEP)
        if len(fields) < 6:
            continue
        commit_hash, short_hash, author, email, date_str, message = fields[:6]
        parents = fields[6].strip() if len(fields) > 6 else ""
        is_merge = " " in parents.strip()   # merge commits have 2+ parent hashes

        try:
            # git outputs ISO 8601 with timezone: "2024-01-15 12:34:56 +0530"
            commit_date = datetime.fromisoformat(date_str.strip())
        except ValueError:
            commit_date = datetime.now(timezone.utc)

        commit_type = classify(message)
        commits.append(CommitData(
            commit_hash=commit_hash.strip(),
            short_hash=short_hash.strip(),
            author=author.strip(),
            author_email=email.strip(),
            commit_date=commit_date,
            message=message.strip(),
            commit_type=commit_type,
            is_merge=is_merge,
            files=[],           # filled lazily below for recent commits only
            lines_added=0,
            lines_removed=0,
        ))

    # For the most recent 50 commits, fetch file stats (numstat is cheap)
    _enrich_with_numstat(project_path, commits[:50])
    return commits


def _enrich_with_numstat(project_path: str, commits: list[CommitData]) -> None:
    """Add files + line counts to a batch of commits using git diff-tree."""
    for c in commits:
        raw = _git(
            project_path,
            "diff-tree", "--no-commit-id", "-r", "--numstat", c.commit_hash,
        )
        files, added, removed = [], 0, 0
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                try:
                    added   += int(parts[0]) if parts[0] != "-" else 0
                    removed += int(parts[1]) if parts[1] != "-" else 0
                    files.append(parts[2])
                except ValueError:
                    pass
        c.files = files
        c.lines_added = added
        c.lines_removed = removed


# ── File churn ─────────────────────────────────────────────────────────────────

def analyze_file_churn(
    project_path: str,
    commits: Optional[list[CommitData]] = None,
    max_commits: int = 300,
) -> dict[str, ChurnData]:
    """
    Compute churn metrics for every file that has changed in the last max_commits.
    If commits is provided, uses them directly (avoids re-running git log).
    """
    if commits is None:
        commits = analyze_history(project_path, max_commits=max_commits)
        _enrich_with_numstat(project_path, commits)

    now = datetime.now(timezone.utc)
    cutoffs = {
        "7d":  now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "90d": now - timedelta(days=90),
    }

    # file_path → list of (commit_date, commit_type, author)
    file_log: dict[str, list[tuple]] = {}

    for c in commits:
        if not c.files:
            continue
        # Ensure commit_date is timezone-aware
        cdate = c.commit_date
        if cdate.tzinfo is None:
            cdate = cdate.replace(tzinfo=timezone.utc)
        for fp in c.files:
            if fp not in file_log:
                file_log[fp] = []
            file_log[fp].append((cdate, c.commit_type, c.author))

    result: dict[str, ChurnData] = {}

    for fp, entries in file_log.items():
        entries_sorted = sorted(entries, key=lambda x: x[0])
        dates   = [e[0] for e in entries_sorted]
        types   = [e[1] for e in entries_sorted]
        authors = list(dict.fromkeys(e[2] for e in entries_sorted))

        c7  = sum(1 for d in dates if d >= cutoffs["7d"])
        c30 = sum(1 for d in dates if d >= cutoffs["30d"])
        c90 = sum(1 for d in dates if d >= cutoffs["90d"])

        bug_count    = types.count("bug_fix")
        revert_count = types.count("revert")

        # Average interval between commits
        if len(dates) > 1:
            intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]
            avg_interval = sum(intervals) / len(intervals)
        else:
            avg_interval = 0.0

        # Churn score: 0–10
        churn = min(10.0, (
            c30 * 0.4 +               # recent churn is weighted more
            c90 * 0.2 +
            bug_count * 0.8 +         # bugs indicate fragility
            revert_count * 1.0 +      # reverts are a strong signal
            len(authors) * 0.3        # many authors = coordination risk
        ))

        result[fp] = ChurnData(
            file_path=fp,
            commits_7d=c7,
            commits_30d=c30,
            commits_90d=c90,
            commits_total=len(dates),
            unique_authors=authors,
            bug_fix_commits=bug_count,
            revert_commits=revert_count,
            first_commit=dates[0] if dates else None,
            last_commit=dates[-1] if dates else None,
            avg_days_between_commits=round(avg_interval, 1),
            churn_score=round(churn, 2),
        )

    return result


# ── Author stats ───────────────────────────────────────────────────────────────

def get_author_stats(
    project_path: str,
    commits: Optional[list[CommitData]] = None,
) -> list[AuthorData]:
    if commits is None:
        commits = analyze_history(project_path, max_commits=300)

    author_map: dict[str, dict] = {}
    for c in commits:
        key = c.author_email or c.author
        if key not in author_map:
            author_map[key] = {
                "name": c.author,
                "email": c.author_email,
                "commits": [],
                "files": set(),
            }
        author_map[key]["commits"].append(c)
        for f in c.files:
            author_map[key]["files"].add(f)

    result = []
    for data in author_map.values():
        cs = data["commits"]
        dates = sorted(c.commit_date for c in cs)
        result.append(AuthorData(
            name=data["name"],
            email=data["email"],
            commit_count=len(cs),
            bug_fix_count=sum(1 for c in cs if c.commit_type == "bug_fix"),
            lines_added=sum(c.lines_added for c in cs),
            lines_removed=sum(c.lines_removed for c in cs),
            active_files=list(data["files"])[:10],
            first_commit=dates[0] if dates else None,
            last_commit=dates[-1] if dates else None,
        ))

    return sorted(result, key=lambda a: a.commit_count, reverse=True)


# ── Co-change analysis ─────────────────────────────────────────────────────────

def co_changed_files(
    project_path: str,
    target_file: str,
    commits: Optional[list[CommitData]] = None,
    top_n: int = 10,
) -> list[tuple[str, int]]:
    """
    Find files that are frequently changed together with target_file.
    Returns [(file_path, co_change_count)] sorted by frequency desc.
    """
    if commits is None:
        commits = analyze_history(project_path, max_commits=200)

    co: dict[str, int] = {}
    for c in commits:
        if target_file in c.files:
            for f in c.files:
                if f != target_file:
                    co[f] = co.get(f, 0) + 1

    return sorted(co.items(), key=lambda x: x[1], reverse=True)[:top_n]


# ── Quick diff stats ───────────────────────────────────────────────────────────

def parse_diff_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff string."""
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            fp = line[6:].strip()
            if fp and fp != "/dev/null":
                files.append(fp)
        elif line.startswith("+++ ") and not line.startswith("+++ b/"):
            fp = line[4:].strip()
            if fp and fp != "/dev/null":
                files.append(fp)
    return list(dict.fromkeys(files))
