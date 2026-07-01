"""
Onboarding Generator — produces a sequenced, role-aware guide for a new developer.

No LLM required for the core output. Grounded entirely in what ProjectMind
has already analyzed: graph centrality, health scores, stored decisions,
known errors, entry points, and detected patterns.

Usage:
  gen = OnboardingGenerator("/path/to/project")
  guide = gen.generate(role="new backend engineer")
  print(guide.to_markdown())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReadingListEntry:
    rank: int
    file: str
    reason: str
    centrality_score: float
    health_warning: Optional[str] = None


@dataclass
class OnboardingGuide:
    project_name: str
    role: str
    entry_points: list[str]
    reading_list: list[ReadingListEntry]
    key_decisions: list[str]
    gotchas: list[str]        # known errors from memory
    avoid_modules: list[str]  # low-health areas
    patterns: list[str]
    health_summary: str
    stack_summary: str

    def to_markdown(self) -> str:
        lines = [
            f"# Onboarding Guide — {self.project_name}",
            f"**Role:** {self.role}",
            f"**Stack:** {self.stack_summary}",
            f"**Health:** {self.health_summary}",
            "",
            "---",
            "",
            "## 1. Start Here (Entry Points)",
        ]
        for i, ep in enumerate(self.entry_points, 1):
            lines.append(f"{i}. `{ep}`")

        lines += ["", "## 2. Must-Read Files (in order)"]
        lines.append("_Ranked by how many other files depend on them — change these and things break._")
        lines.append("")
        for e in self.reading_list:
            warn = f"  ⚠ {e.health_warning}" if e.health_warning else ""
            lines.append(f"{e.rank}. **`{e.file}`** (centrality: {e.centrality_score}){warn}")
            lines.append(f"   _{e.reason}_")

        if self.key_decisions:
            lines += ["", "## 3. Key Architectural Decisions"]
            lines.append("_Understand these before proposing changes._")
            lines.append("")
            for d in self.key_decisions:
                lines.append(f"- {d}")

        if self.gotchas:
            lines += ["", "## 4. Known Gotchas (Read Before You Code)"]
            for g in self.gotchas:
                lines.append(f"- ⚠ {g}")

        if self.avoid_modules:
            lines += ["", "## 5. Approach With Caution"]
            lines.append("_These areas have low health scores — read carefully before touching._")
            for m in self.avoid_modules:
                lines.append(f"- `{m}`")

        if self.patterns:
            lines += ["", "## 6. Established Patterns"]
            lines.append("_Follow these to stay consistent with the codebase._")
            for p in self.patterns:
                lines.append(f"- {p}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class OnboardingGenerator:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.pm_dir = self.root / ".projectmind"

    def generate(self, role: str = "new developer") -> OnboardingGuide:
        health = self._load_health()
        ctx = self._load_context()
        decisions = self._load_decisions()
        errors = self._load_errors()
        central_files = self._load_central_files()

        entry_points = ctx.get("entry_points", [])[:6]
        patterns = ctx.get("patterns", [])[:8]
        language = ctx.get("language", "unknown")
        frameworks = ctx.get("frameworks", "none")
        architecture = ctx.get("architecture", "unknown")
        stack_summary = f"{language} · {frameworks} · {architecture}"

        overall = health.get("overall", "?")
        sec = health.get("security", "?")
        health_summary = f"{overall}/10  (Security: {sec})"

        # Build reading list from centrality data, annotate with health context
        breakdown = health.get("breakdown", {})
        reading_list = []
        for i, entry in enumerate(central_files[:10], 1):
            file_path = entry.get("file", "")
            score = entry.get("centrality_score", 0)
            reason = _reason_for_file(file_path, ctx)
            health_warning = _health_warning(file_path, breakdown)
            reading_list.append(ReadingListEntry(
                rank=i,
                file=file_path,
                reason=reason,
                centrality_score=score,
                health_warning=health_warning,
            ))

        # Gotchas from stored errors
        gotchas = [e.get("error", "")[:120] for e in errors[:6] if e.get("error")]

        # Low-health areas to flag (high security or parse errors)
        avoid = []
        report_path = self.pm_dir / "architecture_report.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
                for issue in report.get("security_issues", [])[:3]:
                    if issue.get("severity") == "error":
                        avoid.append(f"{issue['file']} — security issue: {issue['description'][:60]}")
                for circ in report.get("circular_dependencies", [])[:2]:
                    cycle = " → ".join(circ.get("cycle", [])[:4])
                    avoid.append(f"Circular dep: {cycle}")
            except Exception:
                pass

        return OnboardingGuide(
            project_name=self.root.name,
            role=role,
            entry_points=entry_points,
            reading_list=reading_list,
            key_decisions=decisions,
            gotchas=gotchas,
            avoid_modules=avoid,
            patterns=patterns,
            health_summary=health_summary,
            stack_summary=stack_summary,
        )

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_health(self) -> dict:
        p = self.pm_dir / "health_score.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        return {}

    def _load_context(self) -> dict:
        p = self.pm_dir / "context.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        # Try compressor
        try:
            from backend.core.compression.compressor import Compressor
            return Compressor(str(self.root)).compress()
        except Exception:
            return {}

    def _load_decisions(self) -> list[str]:
        db_path = self.pm_dir / "memory.db"
        if not db_path.exists():
            return []
        try:
            from backend.core.memory.store import MemoryStore
            store = MemoryStore(str(db_path))
            store.init_db()
            decisions = store.list_decisions(str(self.root))
            return [d.decision for d in decisions[:8]]
        except Exception:
            return []

    def _load_errors(self) -> list[dict]:
        db_path = self.pm_dir / "memory.db"
        if not db_path.exists():
            return []
        try:
            from backend.core.memory.store import MemoryStore
            store = MemoryStore(str(db_path))
            store.init_db()
            errors = store.list_errors(str(self.root))
            return [{"error": e.error, "fix": e.fix} for e in errors[:8]]
        except Exception:
            return []

    def _load_central_files(self) -> list[dict]:
        graph_file = self.pm_dir / "knowledge_graph" / "graph.json"
        if not graph_file.exists():
            return []
        try:
            from backend.core.graph.queries import GraphQueries
            from backend.core.graph.serializer import GraphSerializer
            g = GraphSerializer().load(graph_file)
            q = GraphQueries(g, str(self.root))
            return q.most_central(top_n=12)
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------

_REASON_HINTS: list[tuple[str, str]] = [
    ("main",        "application entry point — start here to understand how it boots"),
    ("config",      "configuration — understand settings before changing behavior"),
    ("auth",        "authentication/authorization — critical security boundary"),
    ("model",       "data model — defines the shape of all data in the system"),
    ("schema",      "data schema — defines validation and serialization rules"),
    ("router",      "API routing — maps URLs to handlers"),
    ("middleware",  "middleware — runs on every request"),
    ("database",    "database layer — persistence and query logic"),
    ("service",     "service layer — business logic lives here"),
    ("util",        "utilities — shared helpers used everywhere"),
    ("test",        "test file — understand expected behavior from tests"),
    ("agent",       "AI agent — autonomous decision-making logic"),
    ("graph",       "knowledge graph — relationship and dependency data"),
]


def _reason_for_file(file_path: str, ctx: dict) -> str:
    lower = file_path.lower()
    for hint, reason in _REASON_HINTS:
        if hint in lower:
            return reason
    # Generic fallback
    return "frequently imported — changes here affect many files"


def _health_warning(file_path: str, breakdown: dict) -> Optional[str]:
    if breakdown.get("security_errors", 0) > 0:
        lower = file_path.lower()
        if any(k in lower for k in ["auth", "password", "token", "secret", "crypt"]):
            return "security-sensitive file — review carefully"
    return None
