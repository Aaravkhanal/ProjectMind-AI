"""
Agent nodes for the multi-agent review graph.

Three specialist agents run in parallel (via ThreadPoolExecutor inside
the dispatcher node), then a synthesizer produces the final review.

Each agent now uses the ModelRouter to select the best model for its role
and the task complexity — so the security agent might use DeepSeek R1
while the docs agent uses a fast 8B model, automatically.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.agents.state import ReviewState
from backend.llm.providers import LLM, LLMProvider
from backend.llm.router import ModelRouter, TaskComplexity, classify_task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_ARCHITECT_SYSTEM = """\
You are an expert software architect reviewing a code diff.
Focus ONLY on architectural concerns:
- API design and REST conventions
- Separation of concerns, layering violations
- Code organization and module boundaries
- Scalability and extensibility implications
- Coupling, cohesion, and dependency direction
- Missing abstractions or premature abstractions

Ignore style, formatting, and minor naming issues.
Be concise. Use bullet points. Lead with the most critical findings.
"""

_SECURITY_SYSTEM = """\
You are an expert security engineer reviewing a code diff.
Focus ONLY on security vulnerabilities:
- OWASP Top 10 (injection, broken auth, XSS, IDOR, etc.)
- Secrets or credentials in code
- Input validation and sanitization gaps
- Authentication and authorization flaws
- Insecure dependencies or configurations
- Data exposure risks

Rate each finding: CRITICAL / HIGH / MEDIUM / LOW.
Ignore non-security concerns entirely.
"""

_QUALITY_SYSTEM = """\
You are an expert software engineer reviewing a code diff for code quality.
Focus ONLY on:
- Readability and clarity
- Error handling completeness
- Edge cases that aren't handled
- Test coverage gaps (missing tests for changed logic)
- Performance implications
- Dead code or unnecessary complexity
- Documentation where needed (complex logic, non-obvious invariants)

Ignore architecture and security — those are handled separately.
Be specific: reference line numbers or function names where possible.
"""

_SYNTHESIZER_SYSTEM = """\
You are a senior engineering lead synthesizing three specialist code reviews
into a single, actionable review.

You will receive:
1. An architectural review
2. A security review
3. A code quality review

Your job:
- Merge duplicate findings (don't repeat the same issue three times)
- Prioritise: BLOCKING issues first, then improvements, then nice-to-haves
- Add an executive summary (2-3 sentences) at the top
- Keep the total length under 600 words
- Use clear markdown headers: ## Summary, ## Blocking Issues, ## Improvements, ## Positives

Do NOT add any findings not present in the input reviews.
"""

_USER_TEMPLATE = """\
## Project Context
{project_context}

## Diff
```diff
{diff}
```
"""

_SYNTH_USER_TEMPLATE = """\
## Architectural Review
{architect_review}

---

## Security Review
{security_review}

---

## Code Quality Review
{quality_review}

---

Produce the unified review now.
"""

# ---------------------------------------------------------------------------
# LLM builder — uses router when available, falls back to state credentials
# ---------------------------------------------------------------------------

def _make_chain(
    system: str,
    user_template: str,
    state: ReviewState,
    agent_role: str = "quality",
):
    """
    Build a LangChain chain for the given agent role.

    Model selection priority:
    1. ModelRouter (auto-selects best model for this role + task complexity)
    2. Per-agent override in state["agent_model_overrides"]
    3. Fallback: state["llm_provider"] + state["model_name"]
    """
    overrides: dict = state.get("agent_model_overrides", {})  # type: ignore[attr-defined]

    if agent_role in overrides:
        # Explicit per-agent override from the API caller
        cfg = overrides[agent_role]
        lm = LLM(
            model_name=cfg["model_id"],
            provider=LLMProvider(cfg["provider"]),
            api_key=cfg.get("api_key") or state.get("api_key") or None,
        )
    else:
        # Auto-route based on task complexity
        complexity = TaskComplexity(state.get("task_complexity", TaskComplexity.MEDIUM.value))
        raw_budget = state.get("budget_per_task_usd")  # type: ignore[typeddict-item]
        budget = float(raw_budget) if isinstance(raw_budget, (int, float, str)) else 1.0
        router = ModelRouter(
            preferred_provider=state.get("llm_provider", "nvidia"),
            budget_per_task_usd=budget,
        )
        decision = router.route_for_agent(agent_role, complexity)
        chosen = decision.model
        logger.info(
            "Router → agent=%s model=%s tier=%s  reason: %s",
            agent_role, chosen.model_id, chosen.tier.value, decision.reason[:80],
        )
        lm = LLM(
            model_name=chosen.model_id,
            provider=LLMProvider(chosen.provider),
            api_key=state.get("api_key") or None,
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", user_template),
    ])
    assert lm.model is not None
    return prompt | lm.model | StrOutputParser()


# ---------------------------------------------------------------------------
# Individual agent callers
# ---------------------------------------------------------------------------

def _call_architect(state: ReviewState) -> str:
    chain = _make_chain(_ARCHITECT_SYSTEM, _USER_TEMPLATE, state, "architect")
    return chain.invoke({
        "project_context": state["project_context"],
        "diff": state["diff"],
    })


def _call_security(state: ReviewState) -> str:
    chain = _make_chain(_SECURITY_SYSTEM, _USER_TEMPLATE, state, "security")
    return chain.invoke({
        "project_context": state["project_context"],
        "diff": state["diff"],
    })


def _call_quality(state: ReviewState) -> str:
    chain = _make_chain(_QUALITY_SYSTEM, _USER_TEMPLATE, state, "quality")
    return chain.invoke({
        "project_context": state["project_context"],
        "diff": state["diff"],
    })


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def dispatcher_node(state: ReviewState) -> dict:
    """
    Runs all three specialist agents in parallel.
    Auto-classifies task complexity and routes each agent to the best model.
    """
    # Auto-classify if not already set
    complexity_str = state.get("task_complexity")  # type: ignore[attr-defined]
    if not complexity_str:
        complexity = classify_task(
            description=state.get("pr_info", {}).get("title", ""),
            diff=state["diff"],
        )
        complexity_str = complexity.value
        logger.info("Task classified as: %s", complexity_str)

    tasks = {
        "architect_review": _call_architect,
        "security_review":  _call_security,
        "quality_review":   _call_quality,
    }

    results: dict = {
        "errors": [],
        "task_complexity": complexity_str,
    }
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_key = {executor.submit(fn, state): key for key, fn in tasks.items()}
        for future in as_completed(future_to_key, timeout=180):
            key = future_to_key[future]
            try:
                results[key] = future.result()
                logger.info("Agent %s completed (%d chars)", key, len(results[key]))
            except Exception as exc:
                logger.exception("Agent %s failed: %s", key, exc)
                results[key] = f"[Agent failed: {exc}]"
                results["errors"].append(f"{key}: {exc}")

    return results


def synthesizer_node(state: ReviewState) -> dict:
    """Merges all three specialist reviews into a single unified review."""
    chain = _make_chain(_SYNTHESIZER_SYSTEM, _SYNTH_USER_TEMPLATE, state, "synthesizer")
    try:
        final = chain.invoke({
            "architect_review": state.get("architect_review", ""),
            "security_review":  state.get("security_review", ""),
            "quality_review":   state.get("quality_review", ""),
        })
        return {"final_review": final, "errors": []}
    except Exception as exc:
        logger.exception("Synthesizer failed: %s", exc)
        fallback = "\n\n---\n\n".join(filter(None, [
            state.get("architect_review"),
            state.get("security_review"),
            state.get("quality_review"),
        ]))
        return {
            "final_review": fallback,
            "errors": [f"synthesizer: {exc}"],
        }
