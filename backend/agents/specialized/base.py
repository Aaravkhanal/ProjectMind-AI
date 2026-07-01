"""
Shared base for all specialized agents.

Each specialized agent:
  - Receives a task description + code context
  - Uses ModelRouter to pick the right model for its role
  - Returns a structured artifact (plan / refactored code / tests / docs)
  - Runs as a single LangChain chain (no multi-node graph needed)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.llm.providers import LLM, LLMProvider
from backend.llm.router import ModelRouter, TaskComplexity, classify_task


@dataclass
class AgentInput:
    """Common input for all specialized agents."""
    code: str                          # the code to work on (diff, file, or snippet)
    description: str = ""             # what should be done / task context
    file_path: Optional[str] = None   # hints for language detection
    project_context: str = ""         # compressed .projectmind context (optional)
    language: str = "python"          # target language for output
    llm_provider: str = "nvidia"
    api_key: str = ""
    budget_per_task_usd: float = 1.0
    extra: dict = field(default_factory=dict)   # agent-specific knobs


@dataclass
class AgentOutput:
    """Common output from all specialized agents."""
    artifact: str          # the main output (plan text / code / tests / docs)
    agent: str             # which agent produced this
    model_used: str        # model ID that was selected
    complexity: str        # detected task complexity
    estimated_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


def _build_chain(
    system_prompt: str,
    user_template: str,
    agent_role: str,
    inp: AgentInput,
):
    """
    Build a LangChain LCEL chain for a specialized agent.
    ModelRouter picks the model; falls back to env defaults.
    """
    provider = inp.llm_provider or os.environ.get("LLM_PROVIDER", "nvidia")
    complexity = classify_task(inp.description, inp.code)

    router = ModelRouter(
        preferred_provider=provider,
        budget_per_task_usd=inp.budget_per_task_usd,
    )
    decision = router.route_for_agent(agent_role, complexity)
    chosen = decision.model

    lm = LLM(
        model_name=chosen.model_id,
        provider=LLMProvider(chosen.provider),
        api_key=inp.api_key or None,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", user_template),
    ])
    assert lm.model is not None
    chain = prompt | lm.model | StrOutputParser()
    return chain, decision
