"""
Compressor — converts .projectmind/ files + SQLite memories into a
token-efficient JSON context object that coding agents can consume directly.

Two modes:
  1. template-based (default, no LLM) — pure Python, instant, offline
  2. llm-enhanced (optional)          — LLM summarises long sections
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from backend.core.compression.budget import TokenBudget, coding_agent_budget


# ---------------------------------------------------------------------------
# Template-based extraction helpers
# ---------------------------------------------------------------------------

def _read_md(pm_dir: Path, filename: str) -> str:
    path = pm_dir / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _extract_stack(arch_md: str) -> dict:
    """Pull key-value pairs from ## Stack section of architecture.md."""
    stack: dict[str, str | None] = {}
    in_stack = False
    for line in arch_md.splitlines():
        if line.strip() == "## Stack":
            in_stack = True
            continue
        if in_stack:
            if line.startswith("##"):
                break
            m = re.match(r"-\s+\*\*(.+?):\*\*\s+(.+)", line)
            if m:
                key = m.group(1).lower().replace(" ", "_")
                val = m.group(2).strip()
                stack[key] = None if val in ("none detected", "unknown") else val
    return stack


def _extract_decisions(decisions_md: str) -> list[str]:
    """Return bullet-point decisions from decisions.md (skip headers/empty)."""
    lines = []
    for line in decisions_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("- [ ]"):
            lines.append(stripped[2:])
    return lines


def _extract_coding_style(style_md: str) -> list[str]:
    lines = []
    in_detected = False
    for line in style_md.splitlines():
        if "## Detected Conventions" in line:
            in_detected = True
            continue
        if in_detected:
            if line.startswith("##"):
                break
            stripped = line.strip()
            if stripped.startswith("- ") and not stripped.startswith("- [ ]"):
                lines.append(stripped[2:])
    return lines


def _extract_mistakes(mistakes_md: str) -> list[str]:
    items = []
    for line in mistakes_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("- [ ]"):
            items.append(stripped[2:])
    return items


def _extract_patterns(patterns_md: str) -> list[str]:
    items = []
    for line in patterns_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("- [ ]"):
            items.append(stripped[2:])
        # Also grab table rows (| Pattern | Location | Notes |)
        elif stripped.startswith("|") and not stripped.startswith("| Pattern") and not stripped.startswith("|---"):
            cols = [c.strip() for c in stripped.split("|") if c.strip()]
            if cols and cols[0] != "(add patterns here)":
                items.append(cols[0])
    return items


def _extract_entry_points(arch_md: str) -> list[str]:
    eps = []
    in_ep = False
    for line in arch_md.splitlines():
        if "## Entry Points" in line:
            in_ep = True
            continue
        if in_ep:
            if line.startswith("##"):
                break
            stripped = line.strip()
            m = re.match(r"-\s+`(.+?)`", stripped)
            if m:
                eps.append(m.group(1))
    return eps


def _load_health_score(pm_dir: Path) -> Optional[dict]:
    hp = pm_dir / "health_score.json"
    if hp.exists():
        try:
            return json.loads(hp.read_text())
        except Exception:
            pass
    return None


def _load_memory_summary(pm_dir: Path) -> dict:
    db_path = pm_dir / "memory.db"
    if not db_path.exists():
        return {}
    try:
        from backend.core.memory.store import MemoryStore
        store = MemoryStore(str(db_path))
        store.init_db()
        # Use first known project path or skip
        from sqlmodel import Session, select
        from backend.core.memory.schema import Task
        with Session(store._engine) as session:
            paths = session.exec(select(Task.project_path).distinct()).all()
        if not paths:
            return {}
        return store.get_context_summary(paths[0])
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Main compressor
# ---------------------------------------------------------------------------

class Compressor:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.pm_dir = self.root / ".projectmind"

    def compress(self) -> dict:
        """
        Returns a token-efficient dict representing the project context.
        Budget is used to cap individual sections if provided.
        """
        if not self.pm_dir.exists():
            raise FileNotFoundError(
                f".projectmind/ not found in {self.root}. Run `projectmind init` first."
            )

        arch_md = _read_md(self.pm_dir, "architecture.md")
        style_md = _read_md(self.pm_dir, "coding_style.md")
        decisions_md = _read_md(self.pm_dir, "decisions.md")
        mistakes_md = _read_md(self.pm_dir, "mistakes.md")
        patterns_md = _read_md(self.pm_dir, "patterns.md")

        stack = _extract_stack(arch_md)
        memory = _load_memory_summary(self.pm_dir)
        health = _load_health_score(self.pm_dir)

        context = {
            "project": self.root.name,
            "language": stack.get("language"),
            "frameworks": stack.get("frameworks"),
            "database": stack.get("database"),
            "authentication": stack.get("authentication"),
            "api_style": stack.get("api_style"),
            "architecture": stack.get("architecture"),
            "test_framework": stack.get("testing"),
            "deployment": stack.get("deployment"),
            "entry_points": _extract_entry_points(arch_md),
            "coding_style": _extract_coding_style(style_md),
            "decisions": _extract_decisions(decisions_md) + [
                d["decision"] for d in memory.get("decisions", [])
            ],
            "known_errors": _extract_mistakes(mistakes_md) + [
                f"{e['error']} → {e['fix']}"
                for e in memory.get("known_errors", [])
                if e.get("confidence", 0) >= 0.6
            ],
            "patterns": _extract_patterns(patterns_md),
            "recent_tasks": [
                f"{t['name']} [{t['status']}]"
                for t in memory.get("recent_tasks", [])
            ],
        }

        if health:
            context["health_score"] = health.get("overall")

        # Remove empty lists/None values to save tokens
        context = {k: v for k, v in context.items() if v not in (None, [], {})}

        return context

    def compress_to_json(self) -> str:
        return json.dumps(self.compress(), indent=2)

    def estimate_tokens(self) -> int:
        from backend.core.compression.budget import TokenBudget
        return TokenBudget.estimate(self.compress_to_json())

    def compress_with_budget(self, budget: Optional[TokenBudget] = None) -> dict:
        """Assemble context respecting a token budget; truncates lower-priority sections first."""
        if budget is None:
            budget = coding_agent_budget()

        ctx = self.compress()

        def fmt_list(items: list) -> str:
            return "\n".join(f"- {i}" for i in items)

        stack_text = (
            f"Language: {ctx.get('language', 'unknown')}\n"
            f"Frameworks: {ctx.get('frameworks', 'none')}\n"
            f"Database: {ctx.get('database', 'none')}\n"
            f"Auth: {ctx.get('authentication', 'none')}\n"
            f"API: {ctx.get('api_style', 'none')}\n"
            f"Tests: {ctx.get('test_framework', 'none')}\n"
            f"Deploy: {ctx.get('deployment', 'none')}"
        )

        budget.fill("stack", stack_text)
        budget.fill("coding_style", fmt_list(ctx.get("coding_style", [])))
        budget.fill("decisions", fmt_list(ctx.get("decisions", [])))
        budget.fill("known_errors", fmt_list(ctx.get("known_errors", [])))
        budget.fill("patterns", fmt_list(ctx.get("patterns", [])))
        budget.fill("recent_tasks", fmt_list(ctx.get("recent_tasks", [])))
        budget.fill("architecture", _read_md(self.pm_dir, "architecture.md")[:2000])

        return {
            "context_json": ctx,
            "assembled_text": budget.assemble(),
            "budget": budget.usage_report,
        }
