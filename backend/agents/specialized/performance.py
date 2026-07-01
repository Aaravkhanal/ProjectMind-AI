"""Performance Agent — identifies bottlenecks, memory leaks, O(n) issues, profiling advice."""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """You are a performance engineering expert. Analyze the code for:

1. **Algorithmic Complexity** — O(n²) loops, unnecessary iterations, nested queries
2. **Memory Issues** — leaks, large allocations, inefficient data structures
3. **I/O Bottlenecks** — N+1 queries, missing indexes, blocking calls that should be async
4. **Optimized Version** — rewrite the critical section with explanation
5. **Profiling Advice** — which tool to use and what to look for (cProfile, py-spy, etc.)

Format each issue as:
⚡ **[Issue]** — severity: low/medium/high
- Problem: ...
- Fix: ...
"""

_USER_TMPL = """Language: {language}
File: {file_path}
Context: {description}

Code to analyze:
{code}
"""


def run(inp: AgentInput) -> AgentOutput:
    chain, decision = _build_chain(_SYSTEM, _USER_TMPL, "performance", inp)

    result = chain.invoke({
        "language":    inp.language,
        "file_path":   inp.file_path or "(unknown)",
        "description": inp.description,
        "code":        inp.code,
    })

    return AgentOutput(
        artifact=result.content if hasattr(result, "content") else str(result),
        agent="performance",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
