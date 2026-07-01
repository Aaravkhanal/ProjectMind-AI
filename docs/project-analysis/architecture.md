# Architecture Analysis: ProjectMind AI

## Project Overview
**ProjectMind AI v0.2.0** is a BYOK Multi-Agent AI Engineering Platform built on FastAPI + LangGraph + SQLModel + SQLite. It provides persistent codebase memory, autonomous multi-agent review, planning, execution, and CI/CD integration.

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI / UI Layer                              │
│   (projectmind CLI, VSCode Extension, Web Dashboard, MCP Server)   │
└────────────────┬────────────────────────────────────────┬──────────┘
                 │                                        │
     FastAPI :8000                              VSCode Extension
                 │                                        │
┌────────────────▼────────────────────────────────────────▼──────────┐
│                      API Router Layer (FastAPI)                     │
│  21 route modules · 90+ endpoints                                  │
│  health · analyze · architecture · graph · compress · memory       │
│  prompt · review · agents · advisor · deps · onboarding · adr      │
│  tracer · explain · github_app · models · brain · specialized      │
│  execution · git_intel · cost · providers · code_edit              │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│                   Core Services / Business Logic                    │
│                                                                     │
│  ┌─ Brain ──────────┐  ┌─ Execution ────┐  ┌─ Intelligence ─────┐│
│  │ PR Review track  │  │ Plan execution │  │ Git Intel          ││
│  │ File hotspots    │  │ Step approval  │  │ Risk scoring       ││
│  │ Tech debt        │  │ Agent routing  │  │ Commit classify.   ││
│  │ Contributor stats│  │                │  │ Churn tracking     ││
│  │ Review insights  │  └────────────────┘  └────────────────────┘│
│  └──────────────────┘                                              │
│  ┌─ Memory ─────────┐  ┌─ Agents ───────┐  ┌─ Cost Mgmt ───────┐│
│  │ Task store       │  │ Multi-agent    │  │ Budget limits     ││
│  │ Error memory     │  │ dispatcher     │  │ Cost records      ││
│  │ Decisions        │  │ Architect      │  │ Alerts            ││
│  │ Patterns         │  │ Security       │  │ Model downgrade   ││
│  │ Vector search    │  │ Quality        │  │ Forecasting       ││
│  └──────────────────┘  │ Planner        │  └────────────────────┘│
│                        │ Refactor       │                         │
│  ┌─ Providers ──────┐  │ Testing        │  ┌─ Observability ────┐│
│  │ BYOK key store   │  │ Docs           │  │ Langfuse tracing  ││
│  │ LiteLLM gateway  │  │ BugFix         │  │ Token analytics   ││
│  │ Model profiler   │  │ Performance    │  │ Cost analytics    ││
│  │ Debate/Vote/Refl │  │ DevOps         │  │ Latency tracking  ││
│  └──────────────────┘  │ Code Editor    │  └────────────────────┘│
│                        └────────────────┘                         │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│                   Persistence Layer (SQLite)                        │
│  19 tables across 6 domains:                                       │
│  Brain · Memory · Git Intel · Cost · Execution · Providers         │
│  + Optional ChromaDB for vector search                             │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│                   External Integrations                             │
│  LLM (via LiteLLM): OpenAI · Anthropic · Gemini · Groq            │
│       DeepSeek · Mistral · xAI · Fireworks · NVIDIA · OpenRouter  │
│       Ollama · LM Studio · vLLM · HuggingFace (15+ providers)     │
│  Git: GitHub API · GitLab API · Local repos                        │
│  Observability: Langfuse · OpenTelemetry                           │
└────────────────────────────────────────────────────────────────────┘
```

## Target Architecture (v0.4)

All current components preserved. Additions:
- **LiteLLM gateway** replaces per-provider LangChain bindings
- **BYOK ProviderStore** encrypts and manages all API keys
- **Debate/Vote/Reflect** orchestration modes
- **CodeEditorAgent** with Safe/Approval/Autonomous modes
- **Langfuse** tracing for every LLM call

## Migration Path

| Version | Focus |
|---------|-------|
| v0.2 (now) | BYOK foundation: LiteLLM, encrypted keys, new agents |
| v0.3 | Model profiling, debate mode live, autonomous editing |
| v0.4 | Multi-tenancy, RBAC, audit logs, PostgreSQL option |
