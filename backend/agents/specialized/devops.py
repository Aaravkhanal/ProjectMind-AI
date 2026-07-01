"""DevOps Agent — Dockerfile, CI/CD pipelines, Kubernetes manifests, deployment review."""

from __future__ import annotations

from backend.agents.specialized.base import AgentInput, AgentOutput, _build_chain

_SYSTEM = """You are a senior DevOps engineer. Given infrastructure code (Dockerfile, CI/CD config, k8s manifests, etc.):

1. **Security Issues** — exposed secrets, root containers, wide permissions
2. **Best Practices** — multi-stage builds, layer caching, health checks, resource limits
3. **Reliability** — retry policies, rollback strategy, blue/green vs canary
4. **Optimized Version** — improved version of the config with comments
5. **Pipeline Recommendations** — if CI/CD: missing steps like SAST, DAST, dependency scan

Format:
🐳 **[Issue]** severity: low/medium/high/critical
- Current: ...
- Recommended: ...
"""

_USER_TMPL = """Config type: {config_type}
File: {file_path}
Context: {description}

Config:
{code}
"""


def run(inp: AgentInput) -> AgentOutput:
    config_type = inp.extra.get("config_type", "dockerfile")
    chain, decision = _build_chain(_SYSTEM, _USER_TMPL, "devops", inp)

    result = chain.invoke({
        "config_type": config_type,
        "file_path":   inp.file_path or "(unknown)",
        "description": inp.description,
        "code":        inp.code,
    })

    return AgentOutput(
        artifact=result.content if hasattr(result, "content") else str(result),
        agent="devops",
        model_used=decision.model.model_id,
        complexity=decision.complexity.value,
        estimated_cost_usd=decision.estimated_cost_usd,
    )
