"""
Multi-agent review endpoint.

POST /review/multi-agent
  Runs ArchitectAgent + SecurityAgent + QualityAgent in parallel,
  then synthesizes into a unified review.
  Supports both GitHub PRs and GitLab MRs as diff sources.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review/multi-agent", tags=["agents"])


class MultiAgentReviewRequest(BaseModel):
    # ── diff source (one of: inline diff or GitHub/GitLab PR/MR) ─────────────
    diff: Optional[str] = None

    platform: Optional[Literal["github", "gitlab"]] = None
    git_token: Optional[str] = None

    # GitHub
    owner: Optional[str] = None
    repo: Optional[str] = None
    pr_number: Optional[int] = None

    # GitLab
    project_id: Optional[str] = None
    merge_request_iid: Optional[int] = None

    # ── project context ───────────────────────────────────────────────────────
    project_path: Optional[str] = None   # if set, auto-fetches compressed context

    # ── LLM + model routing ───────────────────────────────────────────────────
    api_key: Optional[str] = None
    llm_provider: str = "openai"
    model: Optional[str] = None
    post_comment: bool = False

    # Multi-model routing controls (all optional — router auto-fills)
    task_complexity: Optional[str] = None          # "simple" | "medium" | "complex"
    budget_per_task_usd: float = 1.0               # hard cost cap per review
    agent_model_overrides: Optional[dict] = None   # {"security": {"provider": "nvidia", "model_id": "..."}}

    @model_validator(mode="after")
    def _validate_diff_source(self) -> "MultiAgentReviewRequest":
        has_inline = bool(self.diff)
        has_platform = bool(self.platform and self.git_token)
        if not has_inline and not has_platform:
            raise ValueError(
                "Provide either `diff` (inline text) or `platform` + `git_token` + PR/MR identifiers."
            )
        return self


class AgentReviewResponse(BaseModel):
    architect_review: str
    security_review: str
    quality_review: str
    final_review: str
    errors: list[str]
    pr_info: Optional[dict] = None
    posted_comment: bool = False
    tokens_saved: Optional[int] = None
    task_complexity: Optional[str] = None   # what the router detected


@router.post("", response_model=AgentReviewResponse)
def multi_agent_review(req: MultiAgentReviewRequest):
    # ── 1. Fetch diff ─────────────────────────────────────────────────────────
    pr_info: dict = {}
    if req.diff:
        diff = req.diff
    else:
        try:
            diff, pr_info = _fetch_diff(req)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch diff: {e}")

    # ── 2. Compressed project context (optional but recommended) ───────────────
    project_context = ""
    tokens_saved = None
    if req.project_path:
        try:
            from backend.core.prompt.generator import SmartPromptGenerator
            result = SmartPromptGenerator(req.project_path).generate(
                task=f"Review this diff: {diff[:200]}..."
            )
            project_context = result["prompt"]
            full_diff_tokens = len(diff) // 4
            tokens_saved = full_diff_tokens - result["token_estimate"]
        except Exception as e:
            logger.warning("Could not load project context from %s: %s", req.project_path, e)

    # ── 3. Run multi-agent graph ───────────────────────────────────────────────
    api_key = req.api_key or os.environ.get("API_KEY", "")
    model = req.model or os.environ.get("CODE_MODEL", "gpt-4o-mini")

    try:
        from backend.agents.graph import run_review
        state = run_review(
            diff=diff,
            project_context=project_context,
            pr_info=pr_info,
            llm_provider=req.llm_provider,
            api_key=api_key,
            model_name=model,
            task_complexity=req.task_complexity or "",
            budget_per_task_usd=req.budget_per_task_usd,
            agent_model_overrides=req.agent_model_overrides or {},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent graph failed: {e}")

    # ── 4. Index into Repository Brain (background, non-blocking) ────────────────
    try:
        from backend.core.brain.indexer import BrainIndexer
        import os as _os
        db_path = _os.environ.get("DB_PATH", ".projectmind/memory.db")
        indexer = BrainIndexer(db_path=db_path)
        indexer.index(
            project_path=req.project_path or ".",
            diff=diff,
            final_review=state["final_review"],
            architect_review=state.get("architect_review", ""),
            security_review=state.get("security_review", ""),
            quality_review=state.get("quality_review", ""),
            pr_info=pr_info,
            task_complexity=state.get("task_complexity", req.task_complexity or "medium"),
            estimated_cost_usd=sum(
                d.get("estimated_cost_usd", 0)
                for d in (state.get("routing_decisions") or {}).values()
            ) if state.get("routing_decisions") else 0.0,
        )
    except Exception as e:
        logger.warning("Brain indexing failed (non-fatal): %s", e)

    # ── 5. Record cost in Cost Optimization Engine (non-blocking) ────────────────
    try:
        import os as _os2
        from backend.core.cost.store import CostStore
        _cost_store = CostStore(db_path=_os2.environ.get("DB_PATH", ".projectmind/memory.db"))
        _cost_store.init_db()
        routing = state.get("routing_decisions") or {}
        _project = req.project_path or "."
        if routing:
            for _role, _d in routing.items():
                _cost_store.record_cost(
                    project_path=_project,
                    operation="review",
                    agent_role=_role,
                    model_id=_d.get("model_id", ""),
                    provider=_d.get("provider", req.llm_provider),
                    model_tier=_d.get("tier", "balanced"),
                    estimated_cost_usd=_d.get("estimated_cost_usd", 0.0),
                    actual_cost_usd=_d.get("estimated_cost_usd", 0.0),
                )
        else:
            # Fallback: record a single entry for the whole review
            _cost_store.record_cost(
                project_path=_project,
                operation="review",
                model_id=model,
                provider=req.llm_provider,
                model_tier="balanced",
                estimated_cost_usd=req.budget_per_task_usd,
                actual_cost_usd=req.budget_per_task_usd,
            )
    except Exception as e:
        logger.warning("Cost recording failed (non-fatal): %s", e)

    # ── 7. Optionally post comment ─────────────────────────────────────────────
    posted = False
    if req.post_comment and state["final_review"] and req.platform:
        try:
            _post_comment(req, state["final_review"])
            posted = True
        except Exception as e:
            logger.warning("Could not post comment: %s", e)

    return AgentReviewResponse(
        architect_review=state["architect_review"],
        security_review=state["security_review"],
        quality_review=state["quality_review"],
        final_review=state["final_review"],
        errors=state["errors"],
        pr_info=pr_info or None,
        posted_comment=posted,
        tokens_saved=tokens_saved,
        task_complexity=state.get("task_complexity"),
    )


# ---------------------------------------------------------------------------
# Helpers (identical pattern to review.py)
# ---------------------------------------------------------------------------

def _fetch_diff(req: MultiAgentReviewRequest) -> tuple[str, dict]:
    if req.platform == "github":
        assert req.git_token and req.owner and req.repo and req.pr_number
        from backend.git.github import GitHubClient
        client = GitHubClient(token=req.git_token)
        diff = client.get_diff(req.owner, req.repo, req.pr_number)
        info = client.get_pr_info(req.owner, req.repo, req.pr_number)
        return diff, info
    else:
        assert req.git_token and req.project_id and req.merge_request_iid
        from backend.git.gitlab import GitLabClient
        client = GitLabClient(token=req.git_token)
        diff = client.get_diff(req.project_id, req.merge_request_iid)
        return diff, {}


def _post_comment(req: MultiAgentReviewRequest, comment: str) -> None:
    if req.platform == "github":
        assert req.git_token and req.owner and req.repo and req.pr_number
        from backend.git.github import GitHubClient
        GitHubClient(token=req.git_token).write_comment(
            req.owner, req.repo, req.pr_number, comment
        )
    elif req.platform == "gitlab":
        assert req.git_token and req.project_id and req.merge_request_iid
        from backend.git.gitlab import GitLabClient
        GitLabClient(token=req.git_token).write_comment(
            req.project_id, req.merge_request_iid, comment
        )
