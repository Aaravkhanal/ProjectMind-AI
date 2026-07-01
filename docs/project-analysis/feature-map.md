# Feature Map: ProjectMind AI

## Status: ✅ Complete · 🚧 Partial · ❌ Not started

## Core Platform

| Feature | Status | Notes |
|---------|--------|-------|
| Project DNA extraction | ✅ | AST + deps + security |
| Persistent SQLite memory | ✅ | 19 tables |
| Vector semantic search | ✅ | ChromaDB (optional) |
| Token compression engine | ✅ | 95%+ reduction |
| Knowledge graph | ✅ | NetworkX + PageRank |
| FastAPI backend | ✅ | 90+ endpoints |
| MCP server | ✅ | Claude Code / Cursor / Windsurf |
| VSCode extension | ✅ | v0.2.0 with sidebar |
| CLI | ✅ | 20+ commands |
| Docker deployment | ✅ | docker-compose |

## BYOK & Multi-Provider

| Feature | Status | Notes |
|---------|--------|-------|
| NVIDIA NIM (14 models) | ✅ | Via ModelRouter |
| OpenAI / Anthropic / Gemini | ✅ | Via ModelRouter |
| **LiteLLM gateway (100+ providers)** | ✅ | New in this update |
| **Encrypted API key storage** | ✅ | Fernet encryption |
| **Provider health checks** | ✅ | `/providers/{p}/test` |
| **Model benchmarking/profiling** | ✅ | `/providers/{p}/benchmark` |
| **Per-task model recommendations** | ✅ | `/providers/recommendations` |
| Ollama / local model support | ✅ | Via LiteLLM |
| LM Studio / vLLM / llama.cpp | ✅ | Via LiteLLM |
| Azure OpenAI / AWS Bedrock | 🚧 | Keys work, not tested |
| API key rotation | ❌ | Planned v0.3 |

## Multi-Agent System

| Feature | Status | Notes |
|---------|--------|-------|
| Architect agent | ✅ | LangGraph node |
| Security agent | ✅ | LangGraph node |
| Quality agent | ✅ | LangGraph node |
| Synthesizer agent | ✅ | LangGraph node |
| Planner agent | ✅ | Specialized chain |
| Refactor agent | ✅ | Specialized chain |
| Testing agent | ✅ | Specialized chain |
| Docs agent | ✅ | Specialized chain |
| **Bug Fix agent** | ✅ | New in this update |
| **Performance agent** | ✅ | New in this update |
| **DevOps agent** | ✅ | New in this update |
| Repository Analyzer agent | 🚧 | Via `/analyze` endpoint |
| Parallel execution | ✅ | ThreadPoolExecutor |

## Agent Orchestration

| Feature | Status | Notes |
|---------|--------|-------|
| Sequential pipeline | ✅ | `/edit/pipeline` |
| Parallel review | ✅ | dispatcher_node |
| **Debate mode** | ✅ | `/providers/debate` |
| **Voting mode** | ✅ | `/providers/vote` |
| **Reflection mode** | ✅ | `/providers/reflect` |
| Agent memory persistence | ✅ | Brain indexer |
| Budget-aware model selection | ✅ | CostOptimizer |

## Autonomous Code Editing

| Feature | Status | Notes |
|---------|--------|-------|
| **Safe mode (suggestions only)** | ✅ | `/edit/plan` |
| **Approval mode (human gate)** | ✅ | `/edit/apply` |
| **Autonomous mode (auto-apply)** | ✅ | `/edit/execute` |
| **Git rollback** | ✅ | git stash + `/edit/rollback` |
| Create / edit / delete files | ✅ | CodeEditorAgent |
| Path traversal protection | ✅ | _safe_path() |
| Secret file blocking | ✅ | _BLOCKED_PATTERNS |
| Auto-PR after edit | ❌ | Planned v0.3 |
| Run tests after edit | ❌ | Planned v0.3 |

## Intelligence & Memory

| Feature | Status | Notes |
|---------|--------|-------|
| Repository Brain | ✅ | 5 tables |
| PR history tracking | ✅ | PRReview |
| File hotspot detection | ✅ | FileHotspot |
| Contributor profiling | ✅ | Contributor |
| Tech debt tracking | ✅ | TechDebt |
| Review insights (auto-gen) | ✅ | ReviewInsight |
| Git commit classification | ✅ | 7 types |
| File churn scoring | ✅ | 3 time windows |
| PR risk scoring | ✅ | 6 factors, 0–10 |
| Short-term memory (task) | ✅ | Task table |
| Long-term memory (decisions) | ✅ | Decision table |
| Bug/error memory | ✅ | ErrorMemory table |
| Architecture memory | ✅ | Pattern + Decision |

## Cost Optimization

| Feature | Status | Notes |
|---------|--------|-------|
| Per-project budgets | ✅ | CostBudget |
| Spend analytics | ✅ | `/cost/summary` |
| Budget alerts | ✅ | Auto-fire at threshold |
| Model downgrade on budget | ✅ | CostOptimizer |
| Monthly forecast | ✅ | Linear projection |
| Per-operation tracking | ✅ | CostRecord |

## Observability

| Feature | Status | Notes |
|---------|--------|-------|
| **Langfuse integration** | ✅ | Optional, env-activated |
| Token analytics | ✅ | Per-review tracking |
| Cost analytics | ✅ | Cost dashboard |
| Latency tracking | ✅ | Per-call |
| Agent execution tracing | 🚧 | Langfuse spans added |
| OpenTelemetry | ❌ | Dependency added, wiring pending |
| Grafana dashboard | ❌ | Planned |

## Integrations

| Feature | Status | Notes |
|---------|--------|-------|
| GitHub PR reviews | ✅ | Webhook + PyGithub |
| GitLab MR reviews | ✅ | Webhook + python-gitlab |
| VSCode extension | ✅ | v0.2.0 |
| MCP server | ✅ | 8 tools |
| CI/CD gate (GitHub Actions) | ✅ | `.github/actions/` |
| Cursor / Windsurf | ✅ | Via MCP |
| JetBrains | ❌ | Planned |
| Slack bot | ❌ | Planned |
| Jira / Linear | ❌ | Planned |

## Enterprise (Future)

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenancy | ❌ | v0.4 |
| RBAC / teams | ❌ | v0.4 |
| SSO / SAML | ❌ | v0.5 |
| Audit logs | ❌ | v0.4 |
| PostgreSQL | ❌ | v0.4 option |
| API key rotation | ❌ | v0.3 |
