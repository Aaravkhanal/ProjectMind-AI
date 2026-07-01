"""
Code review endpoint — supports both GitLab MRs and GitHub PRs.
"""

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from pydantic import BaseModel, model_validator

from backend.git.gitlab import GitLabClient
from backend.git.github import GitHubClient
from backend.llm.providers import LLM, LLMProvider, PromptTemplate
from backend.vector.embeddings import Embeddings
from backend.vector.store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


class ReviewRequest(BaseModel):
    git_token: str
    platform: Literal["gitlab", "github"] = "gitlab"

    # GitLab fields
    project_id: Optional[str] = None
    merge_request_iid: Optional[int] = None

    # GitHub fields
    owner: Optional[str] = None
    repo: Optional[str] = None
    pr_number: Optional[int] = None

    # Common
    api_key: Optional[str] = None
    llm_provider: str = "openai"
    code_model: Optional[str] = None
    conversation_model: Optional[str] = None
    post_comment: bool = False
    knowledge_base_path: Optional[str] = None

    @model_validator(mode="after")
    def _check_required_fields(self) -> "ReviewRequest":
        if self.platform == "gitlab":
            if not self.project_id or not self.merge_request_iid:
                raise ValueError("GitLab reviews require project_id and merge_request_iid")
        elif self.platform == "github":
            if not self.owner or not self.repo or not self.pr_number:
                raise ValueError("GitHub reviews require owner, repo, and pr_number")
        return self


class ReviewResponse(BaseModel):
    content: str
    posted_comment: bool
    platform: str
    pr_info: Optional[dict] = None


def _load_store(kb_path: Optional[str], embedding) -> VectorStore:
    db_path = kb_path or os.environ.get("DB_PATH", "vectorstore/db")
    collection = os.environ.get("COLLECTION_NAME", "good-code")
    store = VectorStore()
    if os.path.exists(db_path):
        return store.load(path=db_path, collection_name=collection, embedding=embedding)
    logger.warning("Knowledge base not found at %s — using empty store.", db_path)
    return store.load(path=db_path, collection_name=collection, embedding=embedding)


def _fetch_diff(req: ReviewRequest) -> tuple[str, dict]:
    """Returns (diff_text, pr_info_dict)."""
    if req.platform == "github":
        assert req.owner and req.repo and req.pr_number  # guaranteed by model_validator
        client = GitHubClient(token=req.git_token)
        diff = client.get_diff(req.owner, req.repo, req.pr_number)
        info = client.get_pr_info(req.owner, req.repo, req.pr_number)
        return diff, info
    else:
        assert req.project_id and req.merge_request_iid  # guaranteed by model_validator
        client = GitLabClient(token=req.git_token)
        diff = client.get_diff(req.project_id, req.merge_request_iid)
        return diff, {}


def _post_comment(req: ReviewRequest, comment: str) -> None:
    if req.platform == "github":
        assert req.owner and req.repo and req.pr_number
        GitHubClient(token=req.git_token).write_comment(
            req.owner, req.repo, req.pr_number, comment
        )
    else:
        assert req.project_id and req.merge_request_iid
        GitLabClient(token=req.git_token).write_comment(
            req.project_id, req.merge_request_iid, comment
        )


@router.post("", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    api_key = req.api_key or os.environ.get("API_KEY", "")
    provider = LLMProvider(req.llm_provider.lower())
    code_model_name = req.code_model or os.environ.get("CODE_MODEL", "gpt-4o-mini")
    conv_model_name = req.conversation_model or os.environ.get("CONVERSATION_MODEL", "gpt-4o-mini")

    embedding = Embeddings.default().embedding

    try:
        kb = _load_store(req.knowledge_base_path, embedding)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load knowledge base: {e}")

    try:
        diff, pr_info = _fetch_diff(req)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch diff: {e}")

    code_llm = LLM(model_name=code_model_name, provider=provider, api_key=api_key)
    conv_llm = LLM(model_name=conv_model_name, provider=provider, api_key=api_key)

    context_prompt = LLM.load_prompt(PromptTemplate.CONTEXT)
    response_prompt = LLM.load_prompt(PromptTemplate.RESPONSE)

    retriever = kb.as_retriever(query=diff, embedding=embedding)

    def format_docs(docs):
        return "\n\n".join(d.page_content for d in docs)

    def extract_json(text: str):
        import json, re
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return text

    def wrap_json(value):
        return {"reviewed_code": value}

    code_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | context_prompt
        | code_llm.model
        | StrOutputParser()
    )

    final_chain = (
        code_chain
        | RunnableLambda(extract_json)
        | RunnableLambda(wrap_json)
        | response_prompt
        | conv_llm.model
        | StrOutputParser()
    )

    try:
        result = final_chain.invoke(diff)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review chain failed: {e}")

    posted = False
    if req.post_comment and result:
        try:
            _post_comment(req, result)
            posted = True
        except Exception as e:
            logger.warning("Could not post comment: %s", e)

    return ReviewResponse(
        content=result,
        posted_comment=posted,
        platform=req.platform,
        pr_info=pr_info or None,
    )
