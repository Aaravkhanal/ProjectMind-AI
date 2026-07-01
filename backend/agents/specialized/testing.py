"""
TestingAgent — generates test cases for code, ready to paste into a test file.

Output: actual runnable test code (pytest by default, configurable).
Covers: happy path, edge cases, error cases, boundary conditions.
"""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """\
You are an expert software engineer specializing in testing.
Generate comprehensive, runnable test cases for the provided code.

Rules:
- Default to pytest (unless the user specifies otherwise in the task)
- Cover: happy path, edge cases, error/exception cases, boundary values
- Each test must have a descriptive name: test_<what>_<when>_<expected>
- Add a short docstring to each test explaining what it verifies
- Use fixtures and parametrize where it reduces duplication
- Mock external dependencies (DB, HTTP, filesystem) — don't call real services
- Tests must be self-contained and importable
- If the code has no testable logic, say so clearly instead of inventing tests

Output ONLY valid, runnable test code. No explanations outside of comments.
Start with the necessary imports, then the test class or functions.
"""

_USER = """\
## Task
{description}

## Code Under Test
File: {file_path}
```{language}
{code}
```

{project_context_section}

{framework_hint}

Generate the test file now.
"""


def run(inp: AgentInput) -> AgentOutput:
    ctx_section = (
        f"## Project Context\n{inp.project_context}" if inp.project_context else ""
    )
    framework = inp.extra.get("test_framework", "pytest")
    framework_hint = f"Use **{framework}** as the test framework." if framework != "pytest" else ""

    chain, decision = _build_chain(_SYSTEM, _USER, "testing", inp)
    try:
        artifact = chain.invoke({
            "description": inp.description or "Generate tests for this code.",
            "file_path": inp.file_path or "unknown",
            "language": inp.language,
            "code": inp.code[:10000],
            "project_context_section": ctx_section,
            "framework_hint": framework_hint,
        })
    except Exception as exc:
        return AgentOutput(
            artifact="",
            agent="testing",
            model_used=decision.model.model_id,
            complexity=decision.complexity.value,
            estimated_cost_usd=decision.estimated_cost_usd,
            errors=[str(exc)],
        )

    return AgentOutput(
        artifact=artifact,
        agent="testing",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
