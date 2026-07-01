"""
BrainIndexer — processes a completed review and writes all brain tables.

Called automatically after every multi-agent review. Extracts:
  - Diff stats from the raw diff
  - Debt signals from the final_review text
  - File-level hotspot bumps
  - Contributor stats
  - Re-aggregates insights every 5 reviews
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from backend.core.brain.store import BrainStore

logger = logging.getLogger(__name__)

# Severity signals in review text → maps to TechDebt.severity
_SEVERITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bCRITICAL\b",  "critical"),
    (r"\bHIGH\b",      "high"),
    (r"\bBLOCKING\b",  "critical"),
    (r"\bMEDIUM\b",    "medium"),
    (r"\bLOW\b",       "low"),
]

# Category keywords in review text
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    (r"\bsecurity\b|\bvulnerabilit\b|\binjection\b|\bauth\b",  "security"),
    (r"\barchitect\b|\bcoupling\b|\blayer\b|\bmodule\b",       "architecture"),
    (r"\btest\b|\bcoverage\b|\bunit test\b",                   "test_coverage"),
    (r"\bdocument\b|\bdocstring\b|\bcomment\b",                "docs"),
]


def _detect_severity(text: str) -> str:
    for pattern, sev in _SEVERITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return sev
    return "medium"


def _detect_category(text: str) -> str:
    for pattern, cat in _CATEGORY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return cat
    return "quality"


def _extract_diff_stats(diff: str) -> dict:
    lines = diff.splitlines()
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files: list[str] = []
    for line in lines:
        if line.startswith("+++ b/") or line.startswith("+++ "):
            fp = line[6:] if line.startswith("+++ b/") else line[4:]
            if fp and fp != "/dev/null":
                files.append(fp.strip())
    return {
        "lines_added": added,
        "lines_removed": removed,
        "files": list(dict.fromkeys(files)),   # deduplicate, preserve order
    }


def _extract_debt_items(review_text: str) -> list[dict]:
    """
    Heuristically extract debt items from the review text.
    Looks for bullet points that describe issues.
    """
    items = []
    for line in review_text.splitlines():
        line = line.strip()
        # Bullet point that looks like an issue
        if not re.match(r"^[-•*]\s+", line) and not re.match(r"^\d+\.\s+", line):
            continue
        content = re.sub(r"^[-•*\d.]\s+", "", line)
        if len(content) < 15:
            continue
        # Skip purely positive statements
        if re.search(r"\bgood\b|\bnice\b|\bwell done\b|\bclean\b|\bexcellent\b", content, re.I):
            continue
        items.append({
            "description": content[:500],
            "severity": _detect_severity(content),
            "category": _detect_category(content),
        })
    return items[:20]   # cap at 20 items per review


def _is_bug_fix(pr_info: dict) -> bool:
    title = (pr_info.get("title") or "").lower()
    labels = [str(l).lower() for l in pr_info.get("labels", [])]
    return (
        any(kw in title for kw in ("fix", "bug", "hotfix", "patch", "regression"))
        or "bug" in labels
        or "fix" in labels
    )


def _score_blocking_issues(review_text: str) -> tuple[int, int]:
    """Returns (blocking_count, suggestion_count) from the review."""
    blocking = len(re.findall(r"\bBLOCKING\b|\bCRITICAL\b", review_text, re.I))
    suggestions = len(re.findall(r"\bsuggest\b|\bconsider\b|\bcould\b|\bmight\b", review_text, re.I))
    return blocking, suggestions


class BrainIndexer:
    """
    Indexes a completed review into the brain tables.
    Designed to be called at the end of multi-agent review routes.
    """

    def __init__(self, db_path: str):
        self.store = BrainStore(db_path=db_path)
        self.store.init_db()

    def index(
        self,
        project_path: str,
        diff: str,
        final_review: str,
        architect_review: str = "",
        security_review: str = "",
        quality_review: str = "",
        pr_info: Optional[dict] = None,
        task_complexity: str = "medium",
        models_used: Optional[list] = None,
        estimated_cost_usd: float = 0.0,
        duration_seconds: Optional[float] = None,
    ) -> dict:
        """
        Full indexing pipeline. Returns a summary of what was written.
        This is safe to call from a background thread — all operations are DB writes.
        """
        pr_info = pr_info or {}
        t0 = time.monotonic()

        # ── 1. Diff stats ─────────────────────────────────────────────────────
        stats = _extract_diff_stats(diff)
        is_bug = _is_bug_fix(pr_info)
        blocking, suggestions = _score_blocking_issues(final_review)

        # ── 2. Approximate scores from review text (0–10) ─────────────────────
        arch_score   = self._text_to_score(architect_review)
        sec_score    = self._text_to_score(security_review)
        qual_score   = self._text_to_score(quality_review)
        overall      = round((arch_score + sec_score + qual_score) / 3, 2) if any(
            [arch_score, sec_score, qual_score]
        ) else None

        # ── 3. Write PRReview ─────────────────────────────────────────────────
        review_record = self.store.record_review(
            project_path=project_path,
            platform=pr_info.get("platform", "local"),
            pr_number=pr_info.get("number"),
            pr_title=pr_info.get("title"),
            author=pr_info.get("author") or pr_info.get("user", {}).get("login"),
            base_branch=pr_info.get("base_branch") or pr_info.get("base", {}).get("ref"),
            files_changed=len(stats["files"]),
            lines_added=stats["lines_added"],
            lines_removed=stats["lines_removed"],
            diff_size_bytes=len(diff.encode()),
            task_complexity=task_complexity,
            models_used=models_used or [],
            architect_score=arch_score,
            security_score=sec_score,
            quality_score=qual_score,
            overall_score=overall,
            blocking_issues=blocking,
            suggestions=suggestions,
            estimated_cost_usd=estimated_cost_usd,
            duration_seconds=duration_seconds,
        )

        # ── 4. Bump file hotspots ─────────────────────────────────────────────
        debt_per_file = (blocking * 0.5) / max(len(stats["files"]), 1)
        for fp in stats["files"]:
            self.store.bump_hotspot(
                project_path=project_path,
                file_path=fp,
                is_bug_fix=is_bug,
                review_flagged=blocking > 0,
                debt_delta=debt_per_file,
            )

        # ── 5. Update contributor ─────────────────────────────────────────────
        author = review_record.author
        if author:
            self.store.update_contributor(
                project_path=project_path,
                author=author,
                diff_size=stats["lines_added"] + stats["lines_removed"],
                quality_score=qual_score,
                security_score=sec_score,
                blocking_issues=blocking,
                files=stats["files"][:5],
            )

        # ── 6. Extract and store tech debt ────────────────────────────────────
        debt_items = _extract_debt_items(final_review)
        for item in debt_items:
            file_hint = stats["files"][0] if stats["files"] else None
            self.store.add_debt(
                project_path=project_path,
                category=item["category"],
                description=item["description"],
                severity=item["severity"],
                file_path=file_hint,
                pr_review_id=review_record.id,
            )

        # ── 7. Re-aggregate insights (every 5 reviews) ────────────────────────
        all_reviews = self.store.list_reviews(project_path, limit=200)
        if len(all_reviews) % 5 == 0 and all_reviews:
            self._refresh_insights(project_path, all_reviews)

        elapsed = round(time.monotonic() - t0, 3)
        logger.info(
            "Brain indexed: project=%s  files=%d  debt_items=%d  elapsed=%.3fs",
            project_path, len(stats["files"]), len(debt_items), elapsed,
        )
        return {
            "pr_review_id": review_record.id,
            "files_indexed": len(stats["files"]),
            "debt_items_added": len(debt_items),
            "overall_score": overall,
            "elapsed_seconds": elapsed,
        }

    @staticmethod
    def _text_to_score(text: str) -> Optional[float]:
        """
        Heuristic: start at 8.0, subtract for red flags, add for praise.
        Returns None if text is empty.
        """
        if not text.strip():
            return None
        score = 8.0
        score -= text.lower().count("critical") * 1.5
        score -= text.lower().count("blocking") * 1.0
        score -= text.lower().count("vulnerability") * 1.0
        score -= text.lower().count("severe") * 0.8
        score -= text.lower().count("bug") * 0.5
        score += text.lower().count("well") * 0.3
        score += text.lower().count("clean") * 0.3
        score += text.lower().count("good") * 0.2
        return round(max(0.0, min(10.0, score)), 2)

    def _refresh_insights(self, project_path: str, reviews: list) -> None:
        """Aggregate review history into human-readable insights."""
        n = len(reviews)
        hotspots = self.store.get_hotspots(project_path, limit=5)
        debt = self.store.list_debt(project_path, resolved=False)
        contributors = self.store.list_contributors(project_path)

        # Insight 1: top debt files
        if hotspots:
            lines = "\n".join(
                f"- `{h.file_path}` — {h.change_count} changes, {h.review_flags} flags, debt={h.debt_score:.1f}"
                for h in hotspots
            )
            self.store.upsert_insight(
                project_path=project_path,
                insight_type="top_debt_files",
                title="Top files accumulating technical debt",
                body=f"Based on {n} reviews:\n\n{lines}",
                data={"files": [h.file_path for h in hotspots]},
                pr_count_basis=n,
            )

        # Insight 2: open debt by category
        by_cat: dict[str, int] = {}
        for d in debt:
            by_cat[d.category] = by_cat.get(d.category, 0) + 1
        if by_cat:
            lines = "\n".join(f"- **{cat}**: {cnt} items" for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]))
            self.store.upsert_insight(
                project_path=project_path,
                insight_type="debt_by_category",
                title="Open technical debt by category",
                body=f"Total open items: {len(debt)}\n\n{lines}",
                data=by_cat,
                pr_count_basis=n,
            )

        # Insight 3: cost trend
        recent = reviews[:10]
        total_cost = sum(r.estimated_cost_usd for r in recent)
        avg_cost = total_cost / len(recent) if recent else 0
        self.store.upsert_insight(
            project_path=project_path,
            insight_type="cost_trend",
            title="Review cost trend (last 10 reviews)",
            body=f"Avg cost per review: **${avg_cost:.4f}**\nTotal (last 10): **${total_cost:.4f}**",
            data={"avg_cost": avg_cost, "total_recent": total_cost},
            pr_count_basis=n,
        )

        # Insight 4: contributor quality
        if contributors:
            top = contributors[0]
            lines = "\n".join(
                f"- **{c.author}**: {c.pr_count} PRs, avg quality={c.avg_quality_score:.1f}, "
                f"blocking={c.blocking_issues_total}"
                for c in contributors[:5]
            )
            self.store.upsert_insight(
                project_path=project_path,
                insight_type="contributor_quality",
                title="Contributor quality signals",
                body=lines,
                data={"top_contributor": top.author},
                pr_count_basis=n,
            )
