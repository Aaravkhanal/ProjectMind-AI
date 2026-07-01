"""
Root Cause Tracer — "What broke this?"

Given an error message or failing test, ProjectMind:
  1. Extracts affected module/file names from the stack trace
  2. Searches memory for similar past errors
  3. Queries git log for recent changes to those files
  4. Checks the knowledge graph for circular deps on that path
  5. Checks health history for regressions near the break time

Returns a ranked list of probable causes with confidence scores.

No LLM required — pure pattern matching + memory lookup.
Optional LLM mode for a narrative explanation.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Cause:
    rank: int
    kind: str           # memory_match | recent_change | circular_dep | health_regression | complexity_spike
    confidence: float   # 0.0–1.0
    description: str
    detail: str         # supporting evidence
    file: Optional[str] = None
    commit: Optional[str] = None


@dataclass
class TraceResult:
    error_summary: str
    affected_files: list[str]
    affected_modules: list[str]
    causes: list[Cause]
    similar_past_errors: list[dict]


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class RootCauseTracer:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.pm_dir = self.root / ".projectmind"

    def trace(self, error_text: str) -> TraceResult:
        affected_files  = _extract_files(error_text, self.root)
        affected_modules = _extract_modules(error_text)
        summary = _summarize_error(error_text)

        causes: list[Cause] = []

        # ── 1. Memory match ───────────────────────────────────────────────
        past = self._search_memory(error_text, affected_modules)
        for i, err in enumerate(past[:3]):
            causes.append(Cause(
                rank=0,
                kind="memory_match",
                confidence=0.9 - i * 0.1,
                description=f"Similar error in project memory: \"{err.get('error', '')[:80]}\"",
                detail=f"Fix used previously: {err.get('fix', '')[:120]}",
                file=None,
            ))

        # ── 2. Recent git changes to affected files ───────────────────────
        recent_changes = self._git_recent_changes(affected_files)
        for change in recent_changes[:5]:
            causes.append(Cause(
                rank=0,
                kind="recent_change",
                confidence=0.7,
                description=f"Recent change to affected file: {change['file']}",
                detail=f"{change['age_days']}d ago — {change['commit']} \"{change['message']}\"",
                file=change["file"],
                commit=change["commit"],
            ))

        # ── 3. Circular dependencies ──────────────────────────────────────
        circ_causes = self._check_circular_deps(affected_modules)
        causes.extend(circ_causes)

        # ── 4. Complexity spike ───────────────────────────────────────────
        complex_causes = self._check_complexity(affected_files)
        causes.extend(complex_causes)

        # ── 5. Health regression around this time ─────────────────────────
        regression_causes = self._check_health_regression()
        causes.extend(regression_causes)

        # Rank by confidence descending
        causes_ranked = sorted(causes, key=lambda c: -c.confidence)
        for i, c in enumerate(causes_ranked, 1):
            c.rank = i

        return TraceResult(
            error_summary=summary,
            affected_files=affected_files,
            affected_modules=affected_modules,
            causes=causes_ranked[:10],
            similar_past_errors=[{"error": e.get("error", ""), "fix": e.get("fix", "")} for e in past[:3]],
        )

    # ------------------------------------------------------------------
    # Analysis methods
    # ------------------------------------------------------------------

    def _search_memory(self, error_text: str, modules: list[str]) -> list[dict]:
        db = self.pm_dir / "memory.db"
        if not db.exists():
            return []
        try:
            from backend.core.memory.store import MemoryStore
            store = MemoryStore(str(db), enable_vectors=False)
            store.init_db()
            errors = store.list_errors(str(self.root))

            # Simple keyword overlap scoring
            error_words = set(re.findall(r"\w+", error_text.lower()))
            scored = []
            for e in errors:
                e_words = set(re.findall(r"\w+", (e.error + " " + e.fix).lower()))
                overlap = len(error_words & e_words) / max(len(error_words), 1)
                if overlap > 0.1 or any(m.lower() in e.error.lower() for m in modules):
                    scored.append((overlap, {"error": e.error, "fix": e.fix, "confidence": e.confidence}))
            scored.sort(key=lambda x: -x[0])
            return [s[1] for s in scored[:5]]
        except Exception:
            return []

    def _git_recent_changes(self, files: list[str]) -> list[dict]:
        if not files:
            return []
        results = []
        for rel_path in files[:8]:
            try:
                r = subprocess.run(
                    ["git", "log", "--since=14.days", "--pretty=format:%h|%cr|%s", "--", rel_path],
                    cwd=str(self.root), capture_output=True, text=True, timeout=8,
                )
                if r.returncode == 0 and r.stdout.strip():
                    for line in r.stdout.splitlines()[:3]:
                        parts = line.split("|", 2)
                        if len(parts) == 3:
                            commit, age_str, message = parts
                            days = _parse_age_to_days(age_str)
                            results.append({
                                "file": rel_path,
                                "commit": commit,
                                "age_days": days,
                                "message": message[:80],
                            })
            except Exception:
                pass
        return sorted(results, key=lambda x: x["age_days"])

    def _check_circular_deps(self, modules: list[str]) -> list[Cause]:
        report = self.pm_dir / "architecture_report.json"
        if not report.exists():
            return []
        try:
            data = json_loads_safe(report)
            causes = []
            for circ in data.get("circular_dependencies", []):
                cycle = circ.get("cycle", [])
                for mod in modules:
                    if any(mod.lower() in c.lower() for c in cycle):
                        cycle_str = " → ".join(cycle[:5])
                        causes.append(Cause(
                            rank=0,
                            kind="circular_dep",
                            confidence=0.75,
                            description=f"Circular dependency involves `{mod}`",
                            detail=f"Cycle: {cycle_str}",
                        ))
                        break
            return causes
        except Exception:
            return []

    def _check_complexity(self, files: list[str]) -> list[Cause]:
        report = self.pm_dir / "architecture_report.json"
        if not report.exists():
            return []
        try:
            data = json_loads_safe(report)
            causes = []
            for fn in data.get("high_complexity_functions", []):
                fn_file = fn.get("file", "")
                if any(fn_file in f or f in fn_file for f in files):
                    causes.append(Cause(
                        rank=0,
                        kind="complexity_spike",
                        confidence=0.5,
                        description=f"High-complexity function: `{fn.get('name', '?')}` (complexity: {fn.get('complexity', '?')})",
                        detail=f"In {fn_file}:{fn.get('line', '?')} — hard to reason about, likely bug source",
                        file=fn_file,
                    ))
            return causes[:3]
        except Exception:
            return []

    def _check_health_regression(self) -> list[Cause]:
        from backend.core.diff.snapshots import load_snapshots
        snaps = load_snapshots(self.pm_dir, limit=3)
        if len(snaps) < 2:
            return []
        latest = snaps[0].get("health", {})
        prev   = snaps[1].get("health", {})
        causes = []
        sec_delta = latest.get("security", 0) - prev.get("security", 0)
        if sec_delta < -1.5:
            causes.append(Cause(
                rank=0,
                kind="health_regression",
                confidence=0.55,
                description=f"Security score regressed recently ({sec_delta:+.1f})",
                detail=(
                    f"Security went from {prev.get('security', '?'):.1f} to {latest.get('security', '?'):.1f} "
                    f"in the last analysis run. A security-related change may have introduced the bug."
                ),
            ))
        return causes


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_FILE_PATTERNS = [
    re.compile(r'File "([^"]+\.py)", line \d+'),      # Python traceback
    re.compile(r"at ([^\s]+\.(?:ts|js|tsx|jsx)):\d+"),  # JS/TS stack
    re.compile(r"FAILED ([^\s:]+\.py)::"),             # pytest
    re.compile(r"([a-zA-Z0-9_/\-\.]+\.py):\d+"),      # generic py
]

_MODULE_PATTERNS = [
    re.compile(r"(?:ModuleNotFoundError|ImportError|cannot import name)[:\s]+['\"]*([a-zA-Z0-9_\.]+)"),
    re.compile(r"AttributeError.*'([a-zA-Z0-9_]+)'"),
    re.compile(r"NameError.*'([a-zA-Z0-9_]+)'"),
    re.compile(r"in ([a-zA-Z0-9_]+)\n"),               # "in function_name" lines
]


def _extract_files(error_text: str, root: Path) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for pattern in _FILE_PATTERNS:
        for m in pattern.finditer(error_text):
            raw = m.group(1)
            # Make relative to project root if possible
            try:
                rel = str(Path(raw).relative_to(root))
            except (ValueError, TypeError):
                rel = raw
            if rel not in seen and not rel.startswith("<"):
                seen.add(rel)
                files.append(rel)
    return files[:10]


def _extract_modules(error_text: str) -> list[str]:
    modules: set[str] = set()
    for pattern in _MODULE_PATTERNS:
        for m in pattern.finditer(error_text):
            name = m.group(1).strip("'\"")
            if len(name) > 1 and not name.isdigit():
                modules.add(name)
    return list(modules)[:8]


def _summarize_error(error_text: str) -> str:
    lines = [l.strip() for l in error_text.strip().splitlines() if l.strip()]
    # Last non-empty line is usually the error message
    for line in reversed(lines):
        if any(kw in line for kw in ["Error", "Exception", "FAILED", "AssertionError", "TypeError"]):
            return line[:120]
    return lines[-1][:120] if lines else error_text[:120]


def _parse_age_to_days(age_str: str) -> int:
    age_str = age_str.strip()
    m = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)", age_str)
    if not m:
        return 999
    n, unit = int(m.group(1)), m.group(2)
    mul = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
    return n * mul.get(unit, 1)


def json_loads_safe(path: Path) -> dict:
    return __import__("json").loads(path.read_text(encoding="utf-8"))
