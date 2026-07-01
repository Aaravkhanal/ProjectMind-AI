"""
Advanced Agent Orchestration Modes.

DebateMode    — same prompt → N models → synthesize winner
VotingMode    — N models vote → majority answer
ReflectionMode— single model critiques its own response
SequentialPipeline — chained agents where each builds on prior output
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrchestrationResult:
    mode: str
    final_answer: str
    participants: list[dict] = field(default_factory=list)   # [{model, response, score}]
    winner: Optional[str] = None
    winner_model: Optional[str] = None
    synthesis_reasoning: str = ""
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0


# ── Debate Mode ─────────────────────────────────────────────────────────────────

_DEBATE_SYNTHESIZER_PROMPT = """You are a neutral judge evaluating multiple AI responses to the same question.

Question asked:
{question}

Responses from different models:
{responses}

Your task:
1. Score each response 1–10 for: accuracy, depth, clarity, actionability
2. Identify which response is BEST overall and why
3. Write a final SYNTHESIS that combines the best insights from all responses

Format:
## Scores
- Model A: X/10 — [one-line reason]
- Model B: X/10 — [one-line reason]

## Winner
Model X — [2-sentence explanation]

## Final Synthesis
[Combined best answer — comprehensive, actionable]
"""


def debate(
    question: str,
    models: list[str],
    project_path: str = ".",
    db_path: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    synthesizer_model: Optional[str] = None,
) -> OrchestrationResult:
    """
    Route the same question to multiple models simultaneously.
    A synthesizer model judges the responses and writes a final answer.

    Args:
        models: list of model IDs (e.g. ["claude-sonnet-4-6", "gpt-4o", "deepseek-chat"])
        synthesizer_model: model to use for judging (defaults to first available powerful model)
    """
    from backend.llm.litellm_gateway import LiteLLMGateway

    db = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
    gateway = LiteLLMGateway(project_path=project_path, db_path=db)

    messages = [{"role": "user", "content": question}]
    responses = gateway.complete_parallel(models, messages, temperature=temperature, max_tokens=max_tokens)

    participants = []
    total_cost   = sum(r.cost_usd for r in responses)
    total_latency= max((r.latency_ms for r in responses), default=0)

    for i, resp in enumerate(responses):
        participants.append({
            "model":    models[i],
            "response": resp.text,
            "cost_usd": resp.cost_usd,
            "latency_ms": resp.latency_ms,
            "error": resp.text.startswith("[ERROR:"),
        })

    # Format responses for synthesizer
    formatted = "\n\n".join(
        f"=== {p['model']} ===\n{p['response']}"
        for p in participants
        if not p["error"]
    )

    synth_model = synthesizer_model or _pick_synthesizer(models)
    synth_messages = [{"role": "user", "content": _DEBATE_SYNTHESIZER_PROMPT.format(
        question=question,
        responses=formatted,
    )}]

    synth_resp = gateway.complete(synth_model, synth_messages, temperature=0.1, max_tokens=1500)
    total_cost += synth_resp.cost_usd

    # Parse winner from synthesis
    winner_model = None
    for p in participants:
        if p["model"].split("/")[-1].lower() in synth_resp.text.lower():
            winner_model = p["model"]
            break

    # Extract final synthesis section
    synthesis_text = synth_resp.text
    if "## Final Synthesis" in synthesis_text:
        synthesis_text = synthesis_text.split("## Final Synthesis", 1)[1].strip()

    return OrchestrationResult(
        mode="debate",
        final_answer=synthesis_text,
        participants=participants,
        winner=synthesis_text,
        winner_model=winner_model,
        synthesis_reasoning=synth_resp.text,
        total_cost_usd=total_cost,
        total_latency_ms=total_latency,
    )


# ── Voting Mode ─────────────────────────────────────────────────────────────────

def vote(
    question: str,
    models: list[str],
    project_path: str = ".",
    db_path: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> OrchestrationResult:
    """
    Multiple models answer the same question.
    The most-common answer wins (majority vote).
    Best for factual/classification tasks.
    """
    from backend.llm.litellm_gateway import LiteLLMGateway

    db = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
    gateway = LiteLLMGateway(project_path=project_path, db_path=db)

    messages = [{"role": "user", "content": question}]
    responses = gateway.complete_parallel(models, messages, temperature=temperature, max_tokens=max_tokens)

    participants = []
    answers: list[str] = []

    for i, resp in enumerate(responses):
        answer = resp.text.strip()
        participants.append({"model": models[i], "response": answer, "cost_usd": resp.cost_usd})
        answers.append(answer)

    # Simple voting: find most common first-line / key phrase
    from collections import Counter

    # Normalize: take first sentence as "vote"
    votes = [a.split("\n")[0].split(".")[0].strip()[:80] for a in answers]
    winner_text, count = Counter(votes).most_common(1)[0]

    return OrchestrationResult(
        mode="voting",
        final_answer=f"**Majority answer ({count}/{len(models)} votes):**\n{winner_text}\n\n**All responses:**\n" +
                     "\n---\n".join(f"**{p['model']}**: {p['response']}" for p in participants),
        participants=participants,
        winner=winner_text,
        total_cost_usd=sum(r.cost_usd for r in responses),
        total_latency_ms=max((r.latency_ms for r in responses), default=0),
    )


# ── Reflection Mode ─────────────────────────────────────────────────────────────

def reflect(
    question: str,
    model: str,
    project_path: str = ".",
    db_path: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    reflection_rounds: int = 1,
) -> OrchestrationResult:
    """
    A model generates a response, then critiques and improves its own answer.
    Optionally runs multiple rounds.
    """
    from backend.llm.litellm_gateway import LiteLLMGateway

    db = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
    gateway = LiteLLMGateway(project_path=project_path, db_path=db)

    total_cost = 0.0
    history: list[dict] = []

    # Initial response
    messages = [{"role": "user", "content": question}]
    initial  = gateway.complete(model, messages, temperature=temperature, max_tokens=max_tokens)
    total_cost += initial.cost_usd

    history.append({"round": 0, "type": "initial", "response": initial.text})

    current = initial.text
    for i in range(reflection_rounds):
        critique_prompt = f"""You gave this response to the question "{question[:100]}...":

{current}

Now critique your own answer:
1. What did you get wrong or oversimplify?
2. What important points are missing?
3. Write an IMPROVED version that addresses these gaps.

Format:
## Critique
[What was wrong/missing]

## Improved Answer
[Better version]
"""
        critique_messages = [{"role": "user", "content": critique_prompt}]
        critique = gateway.complete(model, critique_messages, temperature=0.2, max_tokens=max_tokens)
        total_cost += critique.cost_usd

        # Extract improved answer
        improved = critique.text
        if "## Improved Answer" in improved:
            improved = improved.split("## Improved Answer", 1)[1].strip()

        history.append({"round": i + 1, "type": "reflection", "response": critique.text, "improved": improved})
        current = improved

    return OrchestrationResult(
        mode="reflection",
        final_answer=current,
        participants=[{"model": model, "response": h["response"], "round": h["round"]} for h in history],
        winner_model=model,
        synthesis_reasoning="\n\n---\n\n".join(
            f"**Round {h['round']} ({h['type']}):**\n{h['response']}" for h in history
        ),
        total_cost_usd=total_cost,
    )


# ── Sequential Pipeline ──────────────────────────────────────────────────────────

def sequential_pipeline(
    code: str,
    project_path: str = ".",
    db_path: Optional[str] = None,
    stages: Optional[list[str]] = None,
    language: str = "python",
    description: str = "",
) -> OrchestrationResult:
    """
    Run specialized agents sequentially, each building on the previous output.
    Default pipeline: plan → refactor → testing → docs

    Each stage receives the code + previous stage output as context.
    """
    from backend.agents.specialized.base import AgentInput
    from backend.agents.specialized import planner, refactor, testing, docs

    stage_map = {
        "plan":    planner.run,
        "refactor": refactor.run,
        "testing":  testing.run,
        "docs":     docs.run,
    }

    pipeline = stages or ["plan", "refactor", "testing", "docs"]
    db       = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")
    api_key  = os.environ.get("API_KEY", os.environ.get("NVIDIA_API_KEY", ""))

    participants = []
    context = description
    total_cost = 0.0
    current_code = code

    for stage_name in pipeline:
        stage_fn = stage_map.get(stage_name)
        if not stage_fn:
            continue

        inp = AgentInput(
            code=current_code,
            description=context,
            project_context=f"Previous stages: {[p['stage'] for p in participants]}",
            language=language,
            api_key=api_key,
        )

        try:
            output = stage_fn(inp)
            participants.append({
                "stage":    stage_name,
                "agent":    output.agent,
                "model":    output.model_used,
                "artifact": output.artifact,
                "cost_usd": output.estimated_cost_usd,
            })
            total_cost += output.estimated_cost_usd
            # Each stage's artifact becomes the next stage's context
            context = f"Prior {stage_name} output:\n{output.artifact[:500]}"

        except Exception as e:
            participants.append({"stage": stage_name, "error": str(e)})

    final = "\n\n".join(
        f"## {p['stage'].upper()} ({p.get('model','—')})\n{p.get('artifact', p.get('error',''))}"
        for p in participants
    )

    return OrchestrationResult(
        mode="sequential",
        final_answer=final,
        participants=participants,
        total_cost_usd=total_cost,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _pick_synthesizer(models: list[str]) -> str:
    """Pick best available model for synthesis."""
    preference = ["claude-sonnet-4-6", "gpt-4o", "gemini-2.5-flash", "llama-3.3-70b"]
    for m in preference:
        if m not in models:  # avoid judging your own answer
            return m
    return models[0]
