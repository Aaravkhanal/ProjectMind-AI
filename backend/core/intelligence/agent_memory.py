"""
Phase 21 — Agent Memory.

Each agent accumulates a memory of its own performance across runs:
successes, failures, best prompts, average costs, confidence levels,
and preferred workflows. This feeds the Phase 29 self-learning engine.

Storage:
  .brain/agents/{agent_name}/stats.json  — aggregate stats (fast read)
  .brain/decisions.db                    — per-run records (queryable)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from statistics import mean
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.intelligence.schema import AgentPerformance

KNOWN_AGENTS = [
    "architect", "security", "quality", "synthesizer",
    "planner", "refactor", "testing", "documentation",
    "validation", "learning",
]


class AgentMemoryStore:
    def __init__(self, brain_dir: Path):
        self._agents_dir = brain_dir / "agents"
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        db_path = brain_dir / "decisions.db"
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self._engine)

    # ── write ──────────────────────────────────────────────────────────────────

    def record_run(
        self,
        project_path: str,
        agent_name: str,
        task_type: str = "review",
        success: bool = True,
        confidence: float = 0.0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        tokens_used: int = 0,
        model_used: str = "",
        prompt_text: Optional[str] = None,
    ) -> AgentPerformance:
        prompt_hash = (
            hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
            if prompt_text else ""
        )
        record = AgentPerformance(
            project_path=project_path,
            agent_name=agent_name,
            task_type=task_type,
            success=success,
            confidence=confidence,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            model_used=model_used,
            prompt_hash=prompt_hash,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        self._update_stats(agent_name, record, prompt_text)
        return record

    # ── read ───────────────────────────────────────────────────────────────────

    def get_agent_stats(self, project_path: str, agent_name: str) -> dict:
        stats_file = self._stats_path(agent_name)
        if stats_file.exists():
            try:
                return json.loads(stats_file.read_text())
            except Exception:
                pass

        with Session(self._engine) as session:
            rows = list(
                session.exec(
                    select(AgentPerformance).where(
                        AgentPerformance.project_path == project_path,
                        AgentPerformance.agent_name == agent_name,
                    )
                )
            )
        return self._compute_stats(agent_name, rows)

    def get_all_agents_summary(self, project_path: str) -> dict:
        result: dict[str, dict] = {}
        with Session(self._engine) as session:
            all_rows = list(
                session.exec(
                    select(AgentPerformance).where(
                        AgentPerformance.project_path == project_path
                    )
                )
            )
        by_agent: dict[str, list[AgentPerformance]] = {}
        for row in all_rows:
            by_agent.setdefault(row.agent_name, []).append(row)
        for name, rows in by_agent.items():
            result[name] = self._compute_stats(name, rows)
        return result

    def get_best_model(self, agent_name: str) -> Optional[str]:
        stats_file = self._stats_path(agent_name)
        if stats_file.exists():
            try:
                data = json.loads(stats_file.read_text())
                return data.get("best_model")
            except Exception:
                pass
        return None

    # ── internals ─────────────────────────────────────────────────────────────

    def _update_stats(
        self,
        agent_name: str,
        record: AgentPerformance,
        prompt_text: Optional[str],
    ) -> None:
        stats_file = self._stats_path(agent_name)
        try:
            stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}
        except Exception:
            stats = {}

        runs = stats.get("total_runs", 0) + 1
        successes = stats.get("successes", 0) + (1 if record.success else 0)
        failures = stats.get("failures", 0) + (0 if record.success else 1)
        total_cost = stats.get("total_cost_usd", 0.0) + record.cost_usd
        total_tokens = stats.get("total_tokens", 0) + record.tokens_used

        prev_avg_conf = stats.get("avg_confidence", 0.0)
        avg_conf = ((prev_avg_conf * (runs - 1)) + record.confidence) / runs

        prev_avg_lat = stats.get("avg_latency_ms", 0.0)
        avg_lat = ((prev_avg_lat * (runs - 1)) + record.latency_ms) / runs

        model_counts: dict[str, int] = stats.get("model_counts", {})
        if record.model_used:
            model_counts[record.model_used] = model_counts.get(record.model_used, 0) + 1
        best_model = max(model_counts, key=lambda m: model_counts[m]) if model_counts else None

        best_prompts: list[dict] = stats.get("best_prompts", [])
        if prompt_text and record.success and record.confidence >= 0.8:
            entry = {
                "prompt_hash": record.prompt_hash,
                "model": record.model_used,
                "confidence": record.confidence,
                "cost_usd": record.cost_usd,
                "task_type": record.task_type,
            }
            best_prompts = [p for p in best_prompts if p["prompt_hash"] != record.prompt_hash]
            best_prompts.append(entry)
            best_prompts.sort(key=lambda p: p["confidence"], reverse=True)
            best_prompts = best_prompts[:10]

        stats.update({
            "agent_name": agent_name,
            "total_runs": runs,
            "successes": successes,
            "failures": failures,
            "success_rate": round(successes / runs, 4),
            "avg_confidence": round(avg_conf, 4),
            "avg_latency_ms": round(avg_lat, 2),
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_usd": round(total_cost / runs, 6),
            "total_tokens": total_tokens,
            "model_counts": model_counts,
            "best_model": best_model,
            "best_prompts": best_prompts,
        })

        agent_dir = self._agents_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        stats_file.write_text(json.dumps(stats, indent=2))

    def _compute_stats(self, agent_name: str, rows: list[AgentPerformance]) -> dict:
        if not rows:
            return {"agent_name": agent_name, "total_runs": 0}
        successes = sum(1 for r in rows if r.success)
        return {
            "agent_name": agent_name,
            "total_runs": len(rows),
            "successes": successes,
            "failures": len(rows) - successes,
            "success_rate": round(successes / len(rows), 4),
            "avg_confidence": round(mean(r.confidence for r in rows), 4),
            "avg_latency_ms": round(mean(r.latency_ms for r in rows), 2),
            "avg_cost_usd": round(mean(r.cost_usd for r in rows), 6),
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 6),
            "total_tokens": sum(r.tokens_used for r in rows),
        }

    def _stats_path(self, agent_name: str) -> Path:
        return self._agents_dir / agent_name / "stats.json"
