"""
Health score snapshots — auto-saved on every `projectmind analyze` run.

Each snapshot records:
  - Current git commit + branch
  - Full health score + breakdown
  - Timestamp

Stored at: .projectmind/snapshots/<timestamp>-<commit>.json
Kept: last 50 snapshots (older ones auto-pruned).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_MAX_SNAPSHOTS = 50


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_info(project_root: Path) -> dict:
    def _run(*args: str) -> str:
        try:
            r = subprocess.run(
                ["git", *args],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    return {
        "commit": _run("rev-parse", "--short", "HEAD") or "unknown",
        "commit_full": _run("rev-parse", "HEAD") or "unknown",
        "branch": _run("branch", "--show-current") or "unknown",
        "message": _run("log", "-1", "--pretty=%s") or "",
    }


# ---------------------------------------------------------------------------
# Snapshot save / load
# ---------------------------------------------------------------------------

def save_snapshot(pm_dir: Path, health_dict: dict, project_root: Path) -> Path:
    """
    Save a health score snapshot.
    health_dict: the dict written to health_score.json (overall, architecture, …, breakdown)
    Returns the path of the saved snapshot file.
    """
    snaps_dir = pm_dir / "snapshots"
    snaps_dir.mkdir(exist_ok=True)

    git = _git_info(project_root)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{ts}-{git['commit']}.json"

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git": git,
        "health": health_dict,
    }
    path = snaps_dir / filename
    path.write_text(json.dumps(snapshot, indent=2))

    # Prune old snapshots
    all_snaps = sorted(snaps_dir.glob("*.json"))
    for old in all_snaps[:-_MAX_SNAPSHOTS]:
        old.unlink(missing_ok=True)

    return path


def load_snapshots(pm_dir: Path, limit: int = 10) -> list[dict]:
    """Return the N most recent snapshots, newest first."""
    snaps_dir = pm_dir / "snapshots"
    if not snaps_dir.exists():
        return []
    files = sorted(snaps_dir.glob("*.json"), reverse=True)
    result = []
    for f in files[:limit]:
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return result


def load_latest(pm_dir: Path) -> Optional[dict]:
    snaps = load_snapshots(pm_dir, limit=1)
    return snaps[0] if snaps else None


def load_previous(pm_dir: Path) -> Optional[dict]:
    snaps = load_snapshots(pm_dir, limit=2)
    return snaps[1] if len(snaps) >= 2 else None
