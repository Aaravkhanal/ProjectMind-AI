"""
Multi-agent review graph (LangGraph).

Flow:
  START → dispatcher  (3 agents in parallel via ThreadPoolExecutor)
        → synthesizer (merges into unified review)
        → END
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from backend.agents.nodes import dispatcher_node, synthesizer_node
from backend.agents.state import ReviewState


@lru_cache(maxsize=1)
def build_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("dispatcher",  dispatcher_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START,         "dispatcher")
    builder.add_edge("dispatcher",  "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile()


def run_review(
    diff: str,
    project_context: str = "",
    pr_info: dict | None = None,
    llm_provider: str = "openai",
    api_key: str = "",
    model_name: str = "gpt-4o-mini",
    # ── multi-model routing (all optional) ───────────────────────────────────
    task_complexity: str = "",              # auto-detected from diff if blank
    budget_per_task_usd: float = 1.0,
    agent_model_overrides: dict | None = None,
) -> dict:
    """
    Convenience wrapper — runs the full multi-agent review synchronously.

    Returns the final ReviewState dict with keys:
      architect_review, security_review, quality_review, final_review, errors, task_complexity
    """
    graph = build_graph()
    initial: ReviewState = {
        "diff": diff,
        "pr_info": pr_info or {},
        "project_context": project_context,
        "llm_provider": llm_provider,
        "api_key": api_key,
        "model_name": model_name,
        "task_complexity": task_complexity,
        "budget_per_task_usd": budget_per_task_usd,
        "agent_model_overrides": agent_model_overrides or {},
        "architect_review": "",
        "security_review": "",
        "quality_review": "",
        "final_review": "",
        "errors": [],
    }
    return graph.invoke(initial)
