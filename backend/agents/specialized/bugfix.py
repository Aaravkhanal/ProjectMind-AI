"""Bug Fix Agent — analyzes stack traces, identifies root cause, provides fix."""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """You are an expert debugger. Given code and an error (stack trace or description):

1. **Root Cause** — one sentence explaining WHY it fails
2. **Fixed Code** — complete corrected version, fenced in ```{language}
3. **Explanation** — what changed and why
4. **Prevention** — how to prevent this class of bug in the future

Be precise. Only fix the reported bug — don't refactor unrelated code."""


def run(inp: AgentInput) -> AgentOutput:
    error = inp.extra.get("error_text", "")
    user_tmpl = """Language: {language}
File: {file_path}
Error: {error}

Code:
{code}
"""
    chain, decision = _build_chain(_SYSTEM, user_tmpl, "bug_fix", inp)

    result = chain.invoke({
        "language":  inp.language,
        "file_path": inp.file_path or "(unknown)",
        "error":     error or inp.description,
        "code":      inp.code,
    })

    return AgentOutput(
        artifact=result.content if hasattr(result, "content") else str(result),
        agent="bug_fix",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
