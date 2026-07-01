"""
ADR Generator — auto-generates Architecture Decision Records in MADR format.

Two modes:
  1. Detect:  compare current project context with previous snapshot to find
              new frameworks, DBs, auth patterns, or significant health changes.
  2. Generate: produce a MADR-format .md file for a given decision.

Output: docs/adr/NNNN-<slug>.md
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# MADR template
# ---------------------------------------------------------------------------

_MADR_TEMPLATE = """\
# {title}

* **Status:** {status}
* **Date:** {date}
* **Deciders:** {deciders}

## Context and Problem Statement

{context}

## Decision

{decision}

## Consequences

### Positive

{positive}

### Negative / Trade-offs

{negative}

## Related Decisions

{related}
"""


@dataclass
class ADRRecord:
    number: int
    slug: str
    title: str
    status: str
    date: str
    deciders: str
    context: str
    decision: str
    positive: list[str]
    negative: list[str]
    related: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        return _MADR_TEMPLATE.format(
            title=self.title,
            status=self.status,
            date=self.date,
            deciders=self.deciders,
            context=self.context,
            decision=self.decision,
            positive="\n".join(f"* {p}" for p in self.positive) or "* (none identified)",
            negative="\n".join(f"* {n}" for n in self.negative) or "* (none identified)",
            related="\n".join(f"* {r}" for r in self.related) or "* (none)",
        )

    @property
    def filename(self) -> str:
        return f"{self.number:04d}-{self.slug}.md"


# ---------------------------------------------------------------------------
# Change detector
# ---------------------------------------------------------------------------

@dataclass
class DetectedChange:
    kind: str       # framework_added | db_changed | health_regression | pattern_added | security_issue
    title: str
    context: str
    suggested_decision: str
    positive: list[str]
    negative: list[str]
    auto_confidence: float   # 0.0–1.0 (how sure we are this warrants an ADR)


def detect_adr_worthy_changes(pm_dir: Path) -> list[DetectedChange]:
    """
    Compare current context + health with previous snapshots to find changes
    that warrant an ADR.
    """
    from backend.core.diff.snapshots import load_snapshots

    ctx_path = pm_dir / "context.json"
    if not ctx_path.exists():
        return []

    try:
        current_ctx = json.loads(ctx_path.read_text())
    except Exception:
        return []

    snaps = load_snapshots(pm_dir, limit=5)
    changes: list[DetectedChange] = []

    # ── Health regression ──────────────────────────────────────────────
    if len(snaps) >= 2:
        latest = snaps[0].get("health", {})
        prev   = snaps[1].get("health", {})
        overall_delta = latest.get("overall", 0) - prev.get("overall", 0)
        sec_delta     = latest.get("security", 0) - prev.get("security", 0)

        if sec_delta < -1.5:
            changes.append(DetectedChange(
                kind="security_regression",
                title=f"Security regression: score dropped {sec_delta:.1f}",
                context=(
                    f"Project security score dropped from {prev.get('security', '?'):.1f} "
                    f"to {latest.get('security', '?'):.1f}. "
                    f"Security errors: {latest.get('breakdown', {}).get('security_errors', 0)}."
                ),
                suggested_decision="Define a security review process for PRs that touch auth or data handling.",
                positive=["Establishes a security baseline", "Prevents further regression"],
                negative=["Adds review overhead"],
                auto_confidence=0.8,
            ))
        if overall_delta < -2.0:
            changes.append(DetectedChange(
                kind="health_regression",
                title=f"Overall health dropped significantly ({overall_delta:+.1f})",
                context=(
                    f"Health score regressed from {prev.get('overall', '?'):.1f} "
                    f"to {latest.get('overall', '?'):.1f}."
                ),
                suggested_decision="Adopt a no-regression policy: no PR merges that drop health below current baseline.",
                positive=["Stops technical debt accumulation"],
                negative=["May slow down feature development short-term"],
                auto_confidence=0.6,
            ))

    # ── Framework / DB changes ─────────────────────────────────────────
    frameworks_str = current_ctx.get("frameworks", "")
    db_str         = current_ctx.get("database", "")
    arch_str       = current_ctx.get("architecture", "")

    # These are heuristic patterns worth auto-suggesting an ADR for
    _framework_hints = [
        ("redis",       "Redis caching layer added",         "Cache expensive queries in Redis to reduce DB load"),
        ("celery",      "Celery task queue added",           "Offload background tasks to Celery workers"),
        ("graphql",     "GraphQL API added",                 "Expose a GraphQL API alongside REST endpoints"),
        ("kafka",       "Kafka event streaming added",       "Use Kafka for event-driven communication between services"),
        ("websocket",   "WebSocket support added",           "Add real-time communication via WebSocket"),
        ("docker",      "Dockerized deployment added",       "Deploy via Docker containers for reproducibility"),
        ("kubernetes",  "Kubernetes orchestration added",    "Adopt Kubernetes for container orchestration"),
        ("jwt",         "JWT authentication added",          "Use JWT tokens for stateless authentication"),
        ("oauth",       "OAuth2 authentication added",       "Delegate authentication to OAuth2 provider"),
        ("elasticsearch","Elasticsearch added",              "Use Elasticsearch for full-text search"),
        ("s3",          "S3 / cloud object storage added",  "Store binary assets in S3-compatible object storage"),
    ]

    for keyword, title, decision in _framework_hints:
        if keyword in frameworks_str.lower() or keyword in db_str.lower():
            slug = keyword.replace(" ", "-")
            # Only suggest if not already in existing ADRs
            if not _adr_exists(pm_dir.parent, keyword):
                changes.append(DetectedChange(
                    kind="framework_added",
                    title=title,
                    context=f"Detected {keyword} in the project's technology stack.",
                    suggested_decision=decision,
                    positive=["Explicit rationale captured", "Easier to revisit if trade-offs change"],
                    negative=["Documentation overhead"],
                    auto_confidence=0.5,
                ))

    return changes


# ---------------------------------------------------------------------------
# ADR writer
# ---------------------------------------------------------------------------

class ADRGenerator:
    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.adr_dir = self.root / "docs" / "adr"

    def next_number(self) -> int:
        if not self.adr_dir.exists():
            return 1
        existing = list(self.adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if not existing:
            return 1
        return max(int(f.name[:4]) for f in existing) + 1

    def list_adrs(self) -> list[dict]:
        if not self.adr_dir.exists():
            return []
        adrs = []
        for f in sorted(self.adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
            title_line = ""
            status_line = ""
            try:
                for line in f.read_text(encoding="utf-8").splitlines()[:10]:
                    if line.startswith("# "):
                        title_line = line[2:].strip()
                    if "**Status:**" in line:
                        status_line = re.sub(r"\*+Status:\*+\s*", "", line).strip()
            except Exception:
                pass
            adrs.append({"file": f.name, "title": title_line, "status": status_line})
        return adrs

    def create(
        self,
        title: str,
        context: str,
        decision: str,
        positive: Optional[list[str]] = None,
        negative: Optional[list[str]] = None,
        status: str = "accepted",
        deciders: Optional[str] = None,
    ) -> Path:
        self.adr_dir.mkdir(parents=True, exist_ok=True)
        num = self.next_number()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]

        git_user = _git_user(self.root)
        record = ADRRecord(
            number=num,
            slug=slug,
            title=title,
            status=status,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            deciders=deciders or git_user or "team",
            context=context,
            decision=decision,
            positive=positive or ["Explicit rationale captured for future reference"],
            negative=negative or ["Documentation overhead"],
        )
        path = self.adr_dir / record.filename
        path.write_text(record.to_markdown(), encoding="utf-8")

        # Also store in ProjectMind memory
        try:
            from backend.core.memory.store import MemoryStore
            db = self.root / ".projectmind" / "memory.db"
            if db.exists():
                store = MemoryStore(str(db))
                store.init_db()
                store.add_decision(str(self.root), f"[ADR-{num:04d}] {title}: {decision}")
        except Exception:
            pass

        return path

    def from_detected(self, change: DetectedChange) -> Path:
        return self.create(
            title=change.title,
            context=change.context,
            decision=change.suggested_decision,
            positive=change.positive,
            negative=change.negative,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adr_exists(root: Path, keyword: str) -> bool:
    adr_dir = root / "docs" / "adr"
    if not adr_dir.exists():
        return False
    return any(keyword.lower() in f.name.lower() for f in adr_dir.glob("*.md"))


def _git_user(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "config", "user.name"],
            cwd=str(root), capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""
