"""
Semantic Changelog — shows what *architecture* changed between snapshots,
not just which lines changed.

Git log tells you what files changed.
ProjectMind tells you what the *architecture* changed:
  - New circular dependencies introduced
  - Security regressions
  - Dead code cleaned up or accumulated
  - Complexity increases in hot paths
  - Health score trajectory

Data source: .projectmind/snapshots/*.json  (written on every analyze run)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.core.diff.snapshots import load_snapshots


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChangeEvent:
    kind: str           # see _KIND_* constants below
    description: str
    icon: str
    delta: Optional[float] = None   # numeric change where applicable

# Icons per kind
_ICON = {
    "health_improved":           "↑",
    "health_degraded":           "↓",
    "security_improved":         "✓",
    "security_degraded":         "✗",
    "circular_dep_introduced":   "⊗",
    "circular_dep_resolved":     "✓",
    "dead_code_increased":       "🗑",
    "dead_code_decreased":       "✓",
    "complexity_increased":      "⚠",
    "complexity_decreased":      "✓",
    "arch_degraded":             "↓",
    "arch_improved":             "↑",
}


@dataclass
class SnapshotDiff:
    before_commit: str
    after_commit: str
    after_branch: str
    timestamp: str
    overall_before: float
    overall_after: float
    events: list[ChangeEvent]

    @property
    def score_delta(self) -> float:
        return round(self.overall_after - self.overall_before, 1)

    @property
    def direction(self) -> str:
        if self.score_delta >= 0.5:  return "improved"
        if self.score_delta <= -0.5: return "degraded"
        return "stable"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def build_changelog(
    pm_dir: Path,
    limit: int = 8,
    since_ts: str | None = None,
) -> list[SnapshotDiff]:
    """
    Returns a list of SnapshotDiff objects — one per consecutive snapshot pair.
    Newest first.

    since_ts: ISO timestamp string — exclude snapshots older than this.
    """
    snaps = load_snapshots(pm_dir, limit=limit + 1)
    if since_ts:
        snaps = [s for s in snaps if s.get("timestamp", "") >= since_ts]
    if len(snaps) < 2:
        return []

    diffs: list[SnapshotDiff] = []
    for i in range(len(snaps) - 1):
        after  = snaps[i]
        before = snaps[i + 1]
        diffs.append(_diff_pair(before, after))
    return diffs


def format_changelog(diffs: list[SnapshotDiff]) -> str:
    if not diffs:
        return "No snapshots found. Run `projectmind analyze` at least twice."

    lines: list[str] = ["## Semantic Changelog", ""]
    for sd in diffs:
        # Header line
        direction_icon = "↑" if sd.direction == "improved" else ("↓" if sd.direction == "degraded" else "=")
        score_str = f"{sd.overall_before:.1f} → {sd.overall_after:.1f}"
        lines.append(
            f"**{sd.timestamp[:10]}**  "
            f"`{sd.before_commit}` → `{sd.after_commit}` ({sd.after_branch})  "
            f"{direction_icon} {score_str}"
        )
        for ev in sd.events:
            lines.append(f"  {ev.icon}  {ev.description}")
        if not sd.events:
            lines.append("  =  No significant architectural changes")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def _diff_pair(before: dict, after: dict) -> SnapshotDiff:
    bh = before.get("health", before)
    ah = after.get("health", after)
    bb = bh.get("breakdown", {})
    ab = ah.get("breakdown", {})
    bg = before.get("git", {})
    ag = after.get("git", {})

    events: list[ChangeEvent] = []

    # Overall health
    overall_delta = round(ah.get("overall", 0) - bh.get("overall", 0), 1)
    if abs(overall_delta) >= 0.5:
        kind = "health_improved" if overall_delta > 0 else "health_degraded"
        events.append(ChangeEvent(kind=kind, delta=overall_delta,
            icon=_ICON[kind],
            description=f"Overall health {overall_delta:+.1f} ({bh.get('overall', '?'):.1f} → {ah.get('overall', '?'):.1f})"))

    # Security
    sec_delta = round(ah.get("security", 0) - bh.get("security", 0), 1)
    if abs(sec_delta) >= 0.5:
        kind = "security_improved" if sec_delta > 0 else "security_degraded"
        events.append(ChangeEvent(kind=kind, delta=sec_delta,
            icon=_ICON[kind],
            description=f"Security {sec_delta:+.1f}  (errors: {bb.get('security_errors', 0)} → {ab.get('security_errors', 0)}, warnings: {bb.get('security_warnings', 0)} → {ab.get('security_warnings', 0)})"))

    # Circular dependencies
    circ_delta = ab.get("circular_dependencies", 0) - bb.get("circular_dependencies", 0)
    if circ_delta > 0:
        events.append(ChangeEvent(kind="circular_dep_introduced", delta=circ_delta,
            icon=_ICON["circular_dep_introduced"],
            description=f"{circ_delta} new circular dependenc{'y' if circ_delta == 1 else 'ies'} introduced"))
    elif circ_delta < 0:
        events.append(ChangeEvent(kind="circular_dep_resolved", delta=circ_delta,
            icon=_ICON["circular_dep_resolved"],
            description=f"{-circ_delta} circular dependenc{'y' if -circ_delta == 1 else 'ies'} resolved"))

    # Dead code
    dead_before = bb.get("dead_functions", 0) + bb.get("dead_classes", 0)
    dead_after  = ab.get("dead_functions", 0) + ab.get("dead_classes", 0)
    dead_delta  = dead_after - dead_before
    if dead_delta > 2:
        events.append(ChangeEvent(kind="dead_code_increased", delta=dead_delta,
            icon=_ICON["dead_code_increased"],
            description=f"{dead_delta} more dead code items accumulated (functions + classes)"))
    elif dead_delta < -2:
        events.append(ChangeEvent(kind="dead_code_decreased", delta=dead_delta,
            icon=_ICON["dead_code_decreased"],
            description=f"{-dead_delta} dead code items cleaned up"))

    # Complexity
    cx_delta = ab.get("high_complexity_functions", 0) - bb.get("high_complexity_functions", 0)
    if cx_delta > 0:
        events.append(ChangeEvent(kind="complexity_increased", delta=cx_delta,
            icon=_ICON["complexity_increased"],
            description=f"{cx_delta} more high-complexity function(s) (cyclomatic > 10)"))
    elif cx_delta < -1:
        events.append(ChangeEvent(kind="complexity_decreased", delta=cx_delta,
            icon=_ICON["complexity_decreased"],
            description=f"{-cx_delta} high-complexity function(s) refactored"))

    # Architecture score
    arch_delta = round(ah.get("architecture", 0) - bh.get("architecture", 0), 1)
    if abs(arch_delta) >= 1.0:
        kind = "arch_improved" if arch_delta > 0 else "arch_degraded"
        events.append(ChangeEvent(kind=kind, delta=arch_delta,
            icon=_ICON[kind],
            description=f"Architecture score {arch_delta:+.1f}"))

    return SnapshotDiff(
        before_commit=bg.get("commit", "?"),
        after_commit=ag.get("commit", "?"),
        after_branch=ag.get("branch", "?"),
        timestamp=after.get("timestamp", ""),
        overall_before=bh.get("overall", 0),
        overall_after=ah.get("overall", 0),
        events=events,
    )
