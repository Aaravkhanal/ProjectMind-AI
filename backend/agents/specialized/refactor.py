"""
RefactorAgent — analyzes code and produces concrete refactoring suggestions
with before/after code blocks, ready to apply.

Output format:
  ## Summary
  ## Refactoring 1 — <title>
    ### Before
    ### After
    ### Why
  ## Refactoring 2 ...
  ## What NOT to Change
"""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """\
You are an expert software engineer specializing in code refactoring.
Your goal is to make code cleaner, more maintainable, and more efficient
WITHOUT changing external behaviour.

For each refactoring you suggest, provide:
1. A short title (e.g. "Extract validation logic")
2. The BEFORE block (exact code to replace)
3. The AFTER block (the refactored replacement)
4. Why: one sentence — the specific quality improvement

Rules:
- Only suggest refactorings you are confident are safe (no behaviour changes)
- Prefer small, focused refactorings over large rewrites
- Keep the same language and framework style as the input
- If the code is already clean, say so — do NOT manufacture suggestions
- Mark each refactoring: [SAFE] [NEEDS_TESTS] or [RISKY]
- Suggest 1–6 refactorings maximum

Use this exact structure for each:

## Refactoring N — <title> [SAFE|NEEDS_TESTS|RISKY]

### Before
```<lang>
<original code>
```

### After
```<lang>
<refactored code>
```

### Why
<one sentence>
"""

_USER = """\
## Task
{description}

## Code to Refactor
File: {file_path}
```{language}
{code}
```

{project_context_section}

Produce refactoring suggestions now.
"""


def run(inp: AgentInput) -> AgentOutput:
    ctx_section = (
        f"## Project Context\n{inp.project_context}" if inp.project_context else ""
    )

    chain, decision = _build_chain(_SYSTEM, _USER, "refactor", inp)
    try:
        artifact = chain.invoke({
            "description": inp.description or "Refactor this code for clarity and maintainability.",
            "file_path": inp.file_path or "unknown",
            "language": inp.language,
            "code": inp.code[:10000],
            "project_context_section": ctx_section,
        })
    except Exception as exc:
        return AgentOutput(
            artifact="",
            agent="refactor",
            model_used=decision.model.model_id,
            complexity=decision.complexity.value,
            estimated_cost_usd=decision.estimated_cost_usd,
            errors=[str(exc)],
        )

    return AgentOutput(
        artifact=artifact,
        agent="refactor",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
