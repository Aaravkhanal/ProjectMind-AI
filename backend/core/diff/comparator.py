"""
Health score comparator — diffs two snapshots and produces a structured report.

Used by:
  projectmind diff              # latest vs previous snapshot
  projectmind diff --against <ref>  # current vs a git ref (uses worktree)
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ScoreChange:
    name: str
    before: float
    after: float
    delta: float = field(init=False)
    direction: str = field(init=False)  # "up" | "down" | "same"

    def __post_init__(self):
        self.delta = round(self.after - self.before, 1)
        if self.delta > 0.05:
            self.direction = "up"
        elif self.delta < -0.05:
            self.direction = "down"
        else:
            self.direction = "same"


@dataclass
class IssueChange:
    name: str
    before: int
    after: int
    delta: int = field(init=False)

    def __post_init__(self):
        self.delta = self.after - self.before


@dataclass
class DiffReport:
    scores: list[ScoreChange]
    issues: list[IssueChange]
    before_label: str
    after_label: str
    verdict: str          # "improved" | "degraded" | "unchanged"
    verdict_detail: str   # human sentence


# ---------------------------------------------------------------------------
# Core diff logic
# ---------------------------------------------------------------------------

def compare(before: dict, after: dict, before_label: str = "before", after_label: str = "after") -> DiffReport:
    """
    before / after: health dicts with keys: overall, architecture, security,
                    maintainability, code_quality, breakdown
    """
    bh = before.get("health", before)   # snapshot["health"] or health_score.json directly
    ah = after.get("health", after)

    scores = [
        ScoreChange("Overall",         bh.get("overall", 0),          ah.get("overall", 0)),
        ScoreChange("Architecture",    bh.get("architecture", 0),      ah.get("architecture", 0)),
        ScoreChange("Security",        bh.get("security", 0),          ah.get("security", 0)),
        ScoreChange("Maintainability", bh.get("maintainability", 0),   ah.get("maintainability", 0)),
        ScoreChange("Code Quality",    bh.get("code_quality", 0),      ah.get("code_quality", 0)),
    ]

    bb = bh.get("breakdown", {})
    ab = ah.get("breakdown", {})
    issue_keys = [
        ("security_errors",          "Security errors"),
        ("security_warnings",        "Security warnings"),
        ("circular_dependencies",    "Circular deps"),
        ("duplicate_functions",      "Duplicate functions"),
        ("dead_functions",           "Dead functions"),
        ("dead_classes",             "Dead classes"),
        ("high_complexity_functions","High complexity"),
        ("parse_errors",             "Parse errors"),
    ]
    issues = [
        IssueChange(label, bb.get(key, 0), ab.get(key, 0))
        for key, label in issue_keys
    ]

    overall_delta = scores[0].delta
    security_delta = scores[2].delta

    if overall_delta >= 0.5:
        verdict = "improved"
        verdict_detail = f"Overall health improved by {overall_delta:+.1f} points."
    elif overall_delta <= -0.5:
        worst = min(scores[1:], key=lambda s: s.delta)
        verdict = "degraded"
        verdict_detail = (
            f"Overall health dropped by {-overall_delta:.1f} points. "
            f"Biggest regression: {worst.name} ({worst.delta:+.1f})."
        )
        if security_delta < -1.0:
            verdict_detail += " ⚠ Security degraded — review before merging."
    else:
        verdict = "unchanged"
        verdict_detail = "Health scores are essentially unchanged."

    return DiffReport(
        scores=scores,
        issues=issues,
        before_label=before_label,
        after_label=after_label,
        verdict=verdict,
        verdict_detail=verdict_detail,
    )


# ---------------------------------------------------------------------------
# Git worktree analysis (for --against <ref>)
# ---------------------------------------------------------------------------

def analyze_ref(project_root: Path, ref: str) -> Optional[dict]:
    """
    Checkout ref in a temporary git worktree, run full analysis, return
    a health dict compatible with compare(). Returns None on failure.
    """
    worktree_dir = Path(tempfile.mkdtemp(prefix="pm-diff-"))
    try:
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_dir), ref],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip())

        from backend.core.analyzer.ast_parser import ProjectParser
        from backend.core.analyzer.dead_code import DeadCodeDetector
        from backend.core.analyzer.dependency import DependencyAnalyzer
        from backend.core.analyzer.duplicates import DuplicateDetector
        from backend.core.analyzer.reporter import Reporter
        from backend.core.analyzer.security import SecurityScanner

        analyses = ProjectParser(str(worktree_dir)).parse()
        ok = [a for a in analyses if not a.parse_error]
        dep = DependencyAnalyzer(str(worktree_dir), analyses).analyze()
        dup = DuplicateDetector(analyses).detect()
        dead = DeadCodeDetector(analyses).detect()
        sec = SecurityScanner(str(worktree_dir)).scan([a.path for a in ok])
        reporter = Reporter(str(worktree_dir), "python", analyses, dep, dup, dead, sec)
        report = reporter.build()

        return {
            "health": {
                "overall":         report.health.overall,
                "architecture":    report.health.architecture,
                "security":        report.health.security,
                "maintainability": report.health.maintainability,
                "code_quality":    report.health.code_quality,
                "breakdown":       report.health.breakdown,
            },
            "git": {"commit": ref, "branch": ref},
        }
    except Exception as e:
        raise RuntimeError(f"Failed to analyze ref {ref!r}: {e}") from e
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_dir)],
            cwd=str(project_root),
            capture_output=True,
            timeout=15,
        )
        import shutil
        shutil.rmtree(worktree_dir, ignore_errors=True)
