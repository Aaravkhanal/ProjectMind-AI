# ProjectMind AI — Roadmap

## Vision

The persistent memory layer that every AI coding agent will use by default.
Where Copilot autocompletes lines, ProjectMind remembers your entire project's history, architecture, and decisions — and gives agents exactly the context they need, nothing more.

---

## Phase 1 — Foundation ✅ COMPLETE

**Goal:** Core infrastructure that works offline with zero external dependencies.

| # | Feature | Status |
|---|---|---|
| 1.1 | Project DNA Engine (extractor + generator) | ✅ |
| 1.2 | `.projectmind/` directory structure | ✅ |
| 1.3 | Architecture Analyzer (AST, deps, dead code, security) | ✅ |
| 1.4 | Persistent Memory — SQLite (tasks, decisions, errors, patterns) | ✅ |
| 1.5 | Vector Memory — ChromaDB semantic search | ✅ |
| 1.6 | Token Compression Engine (budget-aware, no LLM required) | ✅ |
| 1.7 | Smart Prompt Generator (context + memories → enriched prompt) | ✅ |
| 1.8 | FastAPI backend with 7 route groups | ✅ |
| 1.9 | GitLab MR Code Reviewer (RAG chain, posts comments) | ✅ |
| 1.10 | CLI — init, analyze, compress, generate-prompt, memory | ✅ |
| 1.11 | NVIDIA NIM + OpenAI + Anthropic + Ollama provider support | ✅ |

---

## Phase 2 — Knowledge Graph

**Goal:** Understand relationships between every file, function, class, and decision.

| # | Feature |
|---|---|
| 2.1 | `backend/core/graph/builder.py` — build directed graph from AST analysis |
| 2.2 | `backend/core/graph/queries.py` — impact analysis, dependency paths, centrality |
| 2.3 | `backend/core/graph/serializer.py` — JSON export for API + VS Code |
| 2.4 | `POST /graph/build` + `GET /graph` + `GET /graph/impact` API routes |
| 2.5 | `projectmind graph` CLI command |
| 2.6 | Save graph to `.projectmind/knowledge_graph/graph.json` |

**Unlocks:** "What breaks if I change this file?" queries. Smart context selection for agents.

---

## Phase 3 — Multi-Agent System

**Goal:** Specialist agents that coordinate to review, architect, and implement.

| # | Feature |
|---|---|
| 3.1 | LangGraph orchestrator setup |
| 3.2 | ArchitectAgent — architecture review and recommendations |
| 3.3 | SecurityAgent — dedicated security analysis agent |
| 3.4 | ReviewerAgent — final synthesis and verdict |
| 3.5 | `POST /agents/run` — submit task, get multi-agent result |
| 3.6 | Agent memory — persist each agent's findings to memory store |
| 3.7 | `projectmind review --agents` CLI flag |

**Unlocks:** "@architect review this", "@security scan auth module", parallel specialist reviews.

---

## Phase 4 — VS Code Extension

**Goal:** ProjectMind directly in the editor, zero context switching.

| # | Feature |
|---|---|
| 4.1 | TypeScript extension scaffold (`vscode-extension/`) |
| 4.2 | Sidebar panels: Health, Memory, Architecture, Timeline |
| 4.3 | Command palette: Analyze, Compress, Generate Prompt, Find Similar Bugs |
| 4.4 | Inline code annotations from architecture report |
| 4.5 | Graph visualization (D3.js or built-in VS Code webview) |
| 4.6 | One-click "Generate Agent Prompt" for current file/selection |
| 4.7 | Status bar: project health score |

**Unlocks:** ProjectMind as a first-class VS Code citizen alongside Copilot/Cursor.

---

## Phase 5 — Production Hardening

**Goal:** Safe, multi-user, API-key-gated deployment.

| # | Feature |
|---|---|
| 5.1 | JWT auth middleware on FastAPI |
| 5.2 | API key management (create, rotate, revoke) |
| 5.3 | Organizations + teams + project membership |
| 5.4 | RBAC (owner, admin, member, viewer) |
| 5.5 | Rate limiting per API key |
| 5.6 | Audit logs (who did what, when) |
| 5.7 | Usage metrics (token savings, prompts generated, reviews run) |
| 5.8 | PostgreSQL support (swap from SQLite for teams) |
| 5.9 | Background job queue (Celery or ARQ) for long-running analyses |

**Unlocks:** Multi-user SaaS deployment. Sell to teams.

---

## Phase 6 — Integrations

**Goal:** Meet developers where they already are.

| # | Feature |
|---|---|
| 6.1 | GitHub MR reviewer (port from GitLab) |
| 6.2 | Slack bot — query memory, get health scores, trigger reviews |
| 6.3 | Jira integration — link decisions to tickets |
| 6.4 | Linear integration — same as Jira |
| 6.5 | MCP server — expose ProjectMind to Claude Code, Cursor, Windsurf |
| 6.6 | GitHub Actions / GitLab CI — auto-review on every MR |
| 6.7 | Webhook support — trigger analysis on push |

**Unlocks:** ProjectMind works passively inside existing workflows without manual invocation.

---

## Phase 7 — Advanced Intelligence

**Goal:** Team intelligence, debate mode, architect advisor.

| # | Feature |
|---|---|
| 7.1 | Team Memory — track who added what and why (git blame + decisions) |
| 7.2 | AI Debate Mode — route same question to multiple LLMs, synthesize best answer |
| 7.3 | AI Architect Advisor — "Can this scale to 10M users?", "Should I migrate?" |
| 7.4 | Auto Documentation Generator (ARCHITECTURE.md, API.md, DECISIONS.md) |
| 7.5 | Project Timeline — searchable history of every architectural change |
| 7.6 | Neo4j integration (optional upgrade path from NetworkX) |
| 7.7 | Self-improving memory — confidence scores update based on outcomes |

---

## Phase 8 — Enterprise

**Goal:** On-premise, SOC 2, SAML, air-gapped deployment.

| # | Feature |
|---|---|
| 8.1 | SSO / SAML authentication |
| 8.2 | On-premise Docker deployment with no external LLM calls |
| 8.3 | Billing integration (Stripe) |
| 8.4 | Analytics dashboard |
| 8.5 | Data residency controls |

---

## Metrics That Matter

| Metric | Phase 1 Baseline | Phase 2 Target |
|---|---|---|
| Token reduction | ~95% (template mode) | ~98% (graph-aware) |
| Init time (1k file project) | ~3 sec | ~3 sec |
| Prompt generation | ~50ms | ~50ms |
| Memory search | ~200ms (SQLite) | ~50ms (vector) |
| Review latency | LLM-bound (~10s) | LLM-bound (~8s) |
