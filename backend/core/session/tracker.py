"""
Session Tracker — records what an AI agent does during a coding session
and surfaces it as context at the start of the next session.

This solves the #1 problem with AI coding tools: every conversation
starts cold. ProjectMind remembers the previous session automatically.

Session lifecycle:
  1. Agent calls get_project_context → session starts / resumes
  2. File changes are tracked via git status polling
  3. Session ends when: agent calls end_session(), or >30 min of inactivity
  4. Summary written to memory → injected into next context call

State file: .projectmind/active_session.json
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_SESSION_FILE = "active_session.json"
_STALE_MINUTES = 30  # session is "resumable" for this long after last activity


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    session_id: str
    task: str
    started_at: str
    last_active: str
    files_modified: list[str] = field(default_factory=list)
    uncommitted_files: list[str] = field(default_factory=list)
    patterns_applied: list[str] = field(default_factory=list)
    status: str = "active"     # active | ended | interrupted
    ended_at: Optional[str] = None

    def age_minutes(self) -> float:
        la = datetime.fromisoformat(self.last_active)
        now = datetime.now(timezone.utc)
        return (now - la).total_seconds() / 60

    def is_resumable(self) -> bool:
        return self.status == "active" and self.age_minutes() < _STALE_MINUTES

    def duration_minutes(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        end_str = self.ended_at or self.last_active
        end = datetime.fromisoformat(end_str)
        return (end - start).total_seconds() / 60


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_modified(project_root: Path) -> tuple[list[str], list[str]]:
    """Returns (modified_files, untracked_files) relative to project root."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return [], []
        modified, untracked = [], []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            status = line[:2]
            path = line[3:].strip()
            if "?" in status:
                untracked.append(path)
            else:
                modified.append(path)
        return modified, untracked
    except Exception:
        return [], []


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------

class SessionTracker:
    def __init__(self, pm_dir: Path):
        self._pm_dir = pm_dir
        self._path = pm_dir / _SESSION_FILE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_or_resume(self, task: str) -> tuple[SessionState, bool]:
        """
        Returns (session, is_resumed).
        If a recent active session exists, resumes it.
        Otherwise starts a fresh session.
        """
        existing = self._load()
        if existing and existing.is_resumable():
            existing.last_active = _now()
            existing.task = task  # update task in case it shifted
            self._poll_git_status(existing)
            self._save(existing)
            return existing, True

        # Mark old session as interrupted if it existed
        if existing and existing.status == "active":
            existing.status = "interrupted"
            existing.ended_at = _now()
            self._save_history(existing)

        session = SessionState(
            session_id=str(uuid.uuid4())[:8],
            task=task,
            started_at=_now(),
            last_active=_now(),
        )
        self._poll_git_status(session)
        self._save(session)
        return session, False

    def touch(self) -> None:
        """Update last_active timestamp (call periodically during a session)."""
        s = self._load()
        if s and s.status == "active":
            s.last_active = _now()
            self._poll_git_status(s)
            self._save(s)

    def end_session(self, status: str = "ended") -> Optional[SessionState]:
        """Mark session as ended, write to history, return final state."""
        s = self._load()
        if not s:
            return None
        s.status = status
        s.ended_at = _now()
        self._poll_git_status(s)
        self._save_history(s)
        self._path.unlink(missing_ok=True)
        return s

    def get_active(self) -> Optional[SessionState]:
        s = self._load()
        return s if s and s.is_resumable() else None

    def get_last_completed(self) -> Optional[SessionState]:
        hist = self._history_dir()
        if not hist.exists():
            return None
        files = sorted(hist.glob("*.json"), reverse=True)
        for f in files[:5]:
            try:
                data = json.loads(f.read_text())
                return SessionState(**data)
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Context injection
    # ------------------------------------------------------------------

    def build_context_block(self) -> str:
        """
        Returns a markdown block summarizing the last/active session.
        Injected at the top of get_project_context output.
        """
        active = self.get_active()
        last = self.get_last_completed()
        lines: list[str] = []

        if active:
            age = int(active.age_minutes())
            lines.append(f"## Active Session (started {age} min ago)")
            lines.append(f"**Task:** {active.task}")
            if active.files_modified:
                lines.append(f"**Modified:** {', '.join(active.files_modified[:8])}")
            if active.uncommitted_files:
                lines.append(
                    f"**⚠ Uncommitted changes:** "
                    f"{', '.join(active.uncommitted_files[:5])} — may be incomplete"
                )
        elif last:
            dur = int(last.duration_minutes())
            lines.append(f"## Last Session ({dur} min)")
            lines.append(f"**Task:** {last.task}")
            if last.files_modified:
                lines.append(f"**Modified:** {', '.join(last.files_modified[:8])}")
            if last.uncommitted_files:
                lines.append(
                    f"**⚠ Uncommitted at end:** "
                    f"{', '.join(last.uncommitted_files[:5])} — possibly incomplete"
                )
            verdict = "✓ Ended cleanly" if last.status == "ended" else "⚠ Interrupted without closing"
            lines.append(f"**Status:** {verdict}")

        return "\n".join(lines) if lines else ""

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _poll_git_status(self, s: SessionState) -> None:
        root = self._pm_dir.parent
        modified, untracked = _git_modified(root)
        # Accumulate unique modified files over session lifetime
        new_files = set(s.files_modified) | set(modified)
        s.files_modified = sorted(new_files)[:30]
        s.uncommitted_files = (modified + untracked)[:20]

    def _save(self, s: SessionState) -> None:
        self._path.write_text(json.dumps(asdict(s), indent=2))

    def _save_history(self, s: SessionState) -> None:
        hist = self._history_dir()
        hist.mkdir(exist_ok=True)
        ts = s.ended_at or _now()
        fname = f"{ts[:19].replace(':', '').replace('-', '').replace('T', '-')}-{s.session_id}.json"
        (hist / fname).write_text(json.dumps(asdict(s), indent=2))

    def _load(self) -> Optional[SessionState]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            return SessionState(**data)
        except Exception:
            return None

    def _history_dir(self) -> Path:
        return self._pm_dir / "sessions"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
