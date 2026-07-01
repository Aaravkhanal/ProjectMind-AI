"""
DocsAgent — generates documentation artifacts from code.

Supports three doc types (via inp.extra["doc_type"]):
  "docstrings"  → inline docstrings for every public function/class
  "readme"      → a README section describing the module
  "api"         → OpenAPI-style endpoint documentation (for route files)

Default: "docstrings"
"""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_DOCSTRING_SYSTEM = """\
You are a technical writer who writes clear, accurate code documentation.

For every public function, class, and method in the provided code:
1. Add a one-line summary docstring
2. Add Args/Returns/Raises sections (Google style) where non-obvious
3. Add a short inline comment for any complex or non-obvious logic block

Rules:
- Do NOT change any logic — only add/update docstrings and comments
- Skip trivial one-liners that are self-explanatory from their name
- Keep docstrings concise — under 5 lines for most functions
- Output the COMPLETE file with all documentation added (not diffs)
- Match the existing code style
"""

_README_SYSTEM = """\
You are a technical writer creating README documentation for a code module.

Write a clear README section in this structure:

## <Module Name>

> One-sentence description.

### What it does
2-3 sentences.

### Usage
```<language>
# Minimal working example
```

### API / Key Functions
Table or list of the main public interfaces with one-line descriptions.

### Configuration
Any environment variables or config options.

### Notes
Edge cases, limitations, or things callers should know.

Rules:
- Be accurate — only document what the code actually does
- Examples must be syntactically valid and minimal
- Skip boilerplate that adds no value
"""

_API_SYSTEM = """\
You are a technical writer creating API documentation for web endpoints.

For each route/endpoint in the provided code, document:
- Method + path
- Description (one sentence)
- Request body (fields, types, required/optional)
- Response body (fields, types)
- Status codes
- Example request (curl)
- Example response (JSON)

Format as clean markdown. Group by tag/router if multiple routers.
"""

_DOC_SYSTEMS = {
    "docstrings": _DOCSTRING_SYSTEM,
    "readme":     _README_SYSTEM,
    "api":        _API_SYSTEM,
}

_USER = """\
## Task
{description}

## Code
File: {file_path}
```{language}
{code}
```

{project_context_section}

Generate the documentation now.
"""


def run(inp: AgentInput) -> AgentOutput:
    doc_type = inp.extra.get("doc_type", "docstrings")
    system = _DOC_SYSTEMS.get(doc_type, _DOCSTRING_SYSTEM)
    ctx_section = (
        f"## Project Context\n{inp.project_context}" if inp.project_context else ""
    )

    chain, decision = _build_chain(system, _USER, "docs", inp)
    try:
        artifact = chain.invoke({
            "description": inp.description or f"Generate {doc_type} for this code.",
            "file_path": inp.file_path or "unknown",
            "language": inp.language,
            "code": inp.code[:10000],
            "project_context_section": ctx_section,
        })
    except Exception as exc:
        return AgentOutput(
            artifact="",
            agent="docs",
            model_used=decision.model.model_id,
            complexity=decision.complexity.value,
            estimated_cost_usd=decision.estimated_cost_usd,
            errors=[str(exc)],
        )

    return AgentOutput(
        artifact=artifact,
        agent="docs",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
