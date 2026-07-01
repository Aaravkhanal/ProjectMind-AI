"""
PlannerAgent — turns a feature request into a step-by-step implementation plan.

Output format:
  ## Goal
  ## Steps (numbered, each with: what to do, which files, estimated effort)
  ## Risks
  ## Definition of Done
"""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """\
You are a senior software architect. Your job is to break down a feature request
or task description into a clear, actionable implementation plan.

Output a plan in this exact markdown structure:

## Goal
One sentence — what this plan achieves.

## Steps
Numbered steps. For each step include:
- What to do (clear action verb)
- Which files/modules to touch
- Estimated effort: XS / S / M / L / XL

## Risks & Dependencies
Bullet points — what could go wrong, external dependencies, blocking factors.

## Definition of Done
Bullet checklist — how to know the feature is complete and working.

Rules:
- Be concrete: name actual file paths and function names based on the context provided
- Steps should be in logical order (you can't test what you haven't written)
- Keep total steps between 4 and 12
- No fluff — every sentence should help an engineer execute the plan
"""

_USER = """\
## Task Description
{description}

## Existing Code / Context
```{language}
{code}
```

{project_context_section}

Generate the implementation plan now.
"""


def run(inp: AgentInput) -> AgentOutput:
    ctx_section = (
        f"## Project Context\n{inp.project_context}"
        if inp.project_context
        else ""
    )

    chain, decision = _build_chain(_SYSTEM, _USER, "planner", inp)
    try:
        artifact = chain.invoke({
            "description": inp.description or "Implement the changes shown in the code.",
            "language": inp.language,
            "code": inp.code[:8000],
            "project_context_section": ctx_section,
        })
    except Exception as exc:
        return AgentOutput(
            artifact="",
            agent="planner",
            model_used=decision.model.model_id,
            complexity=decision.complexity.value,
            estimated_cost_usd=decision.estimated_cost_usd,
            errors=[str(exc)],
        )

    return AgentOutput(
        artifact=artifact,
        agent="planner",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
