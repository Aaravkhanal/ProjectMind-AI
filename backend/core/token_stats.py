"""
Token savings tracker — records how many tokens ProjectMind saves per session.

Stored at .projectmind/token_stats.json (plain JSON, no DB required).

Design:
  Every call to get_project_context / compress / generate-prompt records:
    - tokens_used:  size of compressed context sent to LLM
    - tokens_saved: estimated raw codebase size minus compressed size
  Running totals accumulate per project, grouped by month and tool.

Pricing: set PM_PRICE_PER_MILLION_TOKENS env var to match your actual provider.
  GPT-4o input:     $5.00  (default)
  Claude Sonnet 3.5: $3.00
  GPT-4o-mini:      $0.15
  Local (Ollama):   $0.00
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Configurable: set PM_PRICE_PER_MILLION_TOKENS to match your LLM provider
_PRICE_PER_TOKEN = float(os.environ.get("PM_PRICE_PER_MILLION_TOKENS", "5.0")) / 1_000_000


# ---------------------------------------------------------------------------
# Raw codebase size estimator
# ---------------------------------------------------------------------------

_IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".projectmind"}
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php"}


def estimate_raw_tokens(project_root: Path) -> int:
    """Estimate total token count if the entire codebase were sent to an LLM."""
    total_bytes = 0
    for ext in _SOURCE_EXTS:
        for f in project_root.rglob(f"*{ext}"):
            if any(part in _IGNORE for part in f.parts):
                continue
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
    return max(total_bytes // 4, 1)   # ~4 chars per token


# ---------------------------------------------------------------------------
# Token stats store
# ---------------------------------------------------------------------------

class TokenStats:
    """
    Append-only token savings log for a project.
    Thread-unsafe (single-process, same as the rest of the CLI).
    """

    def __init__(self, pm_dir: Path):
        self._path = pm_dir / "token_stats.json"
        self._data: dict = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        tokens_used: int,
        raw_codebase_tokens: int,
        tool: str = "compress",
    ) -> int:
        """
        Record one compression call.
        Returns tokens_saved (raw - used, clamped to 0).
        """
        tokens_saved = max(0, raw_codebase_tokens - tokens_used)
        month = datetime.now(timezone.utc).strftime("%Y-%m")

        self._data["total_calls"] += 1
        self._data["total_tokens_used"] += tokens_used
        self._data["total_tokens_saved"] += tokens_saved
        self._data["raw_codebase_estimate_tokens"] = raw_codebase_tokens
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()

        # By month
        by_month = self._data.setdefault("by_month", {})
        m = by_month.setdefault(month, {"calls": 0, "tokens_saved": 0})
        m["calls"] += 1
        m["tokens_saved"] += tokens_saved

        # By tool
        by_tool = self._data.setdefault("by_tool", {})
        t = by_tool.setdefault(tool, {"calls": 0, "tokens_saved": 0})
        t["calls"] += 1
        t["tokens_saved"] += tokens_saved

        self._save()
        return tokens_saved

    def summary(self) -> dict:
        """Return a human-friendly summary dict."""
        total_saved = self._data.get("total_tokens_saved", 0)
        total_calls = self._data.get("total_calls", 0)
        raw = self._data.get("raw_codebase_estimate_tokens", 0)
        used = self._data.get("total_tokens_used", 0)

        # Current month
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        month_data = self._data.get("by_month", {}).get(month, {})
        month_saved = month_data.get("tokens_saved", 0)
        month_calls = month_data.get("calls", 0)

        avg_compression = (1 - used / max(total_calls * raw, 1)) * 100 if total_calls and raw else 0

        return {
            "total_calls": total_calls,
            "total_tokens_saved": total_saved,
            "total_tokens_used": used,
            "raw_codebase_tokens": raw,
            "avg_compression_pct": round(avg_compression, 1),
            "estimated_cost_saved_usd": round(total_saved * _PRICE_PER_TOKEN, 2),
            "this_month": {
                "calls": month_calls,
                "tokens_saved": month_saved,
                "estimated_cost_saved_usd": round(month_saved * _PRICE_PER_TOKEN, 2),
            },
            "by_tool": self._data.get("by_tool", {}),
            "last_updated": self._data.get("last_updated"),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "total_calls": 0,
            "total_tokens_used": 0,
            "total_tokens_saved": 0,
            "raw_codebase_estimate_tokens": 0,
            "by_month": {},
            "by_tool": {},
            "last_updated": None,
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
