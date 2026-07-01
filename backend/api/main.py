import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local first (takes precedence), then .env as fallback
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local", override=True)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import (
    adr, advisor, agents, analyze, architecture,
    brain, code_edit, compress, cost, deps, discovery, execution, explain, github_app, git_intel, graph, health,
    intelligence, memory, models, onboarding, prompt, providers, review, specialized, tracer,
)
from backend.version import __description__, __title__, __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("ProjectMind AI v%s starting", __version__)
    yield
    logger.info("ProjectMind AI shutting down")


app = FastAPI(
    title=__title__,
    description=__description__,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "health",        "description": "Service health and liveness"},
        {"name": "analyze",       "description": "Project DNA extraction and .projectmind/ initialization"},
        {"name": "architecture",  "description": "Static analysis: dependencies, dead code, security, duplicates"},
        {"name": "graph",         "description": "Knowledge graph: file relationships, impact analysis, centrality"},
        {"name": "compress",      "description": "Token-efficient context compression (no LLM required)"},
        {"name": "memory",        "description": "Persistent project memory: tasks, decisions, errors, patterns"},
        {"name": "prompt",        "description": "Context-enriched prompt generation for AI coding agents"},
        {"name": "review",        "description": "GitLab merge request code review via RAG chain"},
        {"name": "agents",        "description": "Multi-agent parallel review: ArchitectAgent + SecurityAgent + QualityAgent"},
        {"name": "advisor",       "description": "AI Architect Advisor: answer architectural questions from compressed context"},
        {"name": "deps",          "description": "Dependency risk scoring: CVEs, staleness, and import centrality"},
        {"name": "onboarding",    "description": "Onboarding guide generator: role-aware reading list for new developers"},
        {"name": "adr",           "description": "Architecture Decision Records: auto-detect and generate MADR-format ADRs"},
        {"name": "tracer",        "description": "Root cause tracer: find what broke this from error text + memory + git"},
        {"name": "explain",       "description": "Grounded README/architecture doc generator from real analysis data"},
        {"name": "github-app",    "description": "GitHub App webhook: automated PR review and health gate for any repo"},
        {"name": "models",        "description": "Multi-model orchestration: catalog, availability, and automatic model routing"},
        {"name": "brain",             "description": "Repository Brain: PR history, file hotspots, contributor stats, tech debt, and insights"},
        {"name": "specialized-agents", "description": "Specialized AI agents: Planner, Refactor, Testing, Documentation"},
        {"name": "execution",           "description": "Execution planning + human approval: create plans, approve/reject steps, run agents per step"},
        {"name": "git-intelligence",    "description": "Git Intelligence: commit classification, file churn, co-change analysis, PR risk scoring"},
        {"name": "cost",                "description": "Cost Optimization Engine: budget management, spend analytics, model downgrade, forecasting"},
        {"name": "providers",           "description": "BYOK Provider Management: encrypted key storage, health checks, benchmarking, 15+ providers"},
        {"name": "code-editing",        "description": "Autonomous Code Editing: safe/approval/autonomous file edits with git rollback, sequential pipelines"},
        {"name": "environment-discovery", "description": "Phase 20: auto-detect IDEs, providers, local models, MCP servers; capability matrix; intelligent task routing"},
        {"name": "intelligence", "description": "Phase 21–23: Architecture Memory, Decision Store, Agent Memory, Knowledge Graph (KuzuDB), Vector Memory (LanceDB)"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Check server logs for details."},
    )


app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(architecture.router)
app.include_router(graph.router)
app.include_router(compress.router)
app.include_router(memory.router)
app.include_router(prompt.router)
app.include_router(review.router)
app.include_router(agents.router)
app.include_router(advisor.router)
app.include_router(deps.router)
app.include_router(onboarding.router)
app.include_router(adr.router)
app.include_router(tracer.router)
app.include_router(explain.router)
app.include_router(github_app.router)
app.include_router(models.router)
app.include_router(brain.router)
app.include_router(specialized.router)
app.include_router(execution.router)
app.include_router(git_intel.router)
app.include_router(cost.router)
app.include_router(providers.router)
app.include_router(code_edit.router)
app.include_router(discovery.router)
app.include_router(intelligence.router)


def start():
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("ENV", "development") == "development",
        log_level=log_level,
    )


if __name__ == "__main__":
    start()
