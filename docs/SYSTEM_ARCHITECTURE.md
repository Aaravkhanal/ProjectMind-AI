# System Architecture — ProjectMind AI

## The Problem

Every AI coding session starts from zero. The agent reads thousands of files, burns 300k+ tokens, and forgets everything the moment the context window closes. Mistakes repeat. Decisions get re-litigated. The same architecture questions get re-answered every sprint.

## The Solution

ProjectMind is a **persistent memory layer** that sits between your codebase and any AI agent. It analyzes once, remembers forever, and compresses project knowledge into a token budget that fits inside any LLM's context window.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│                                                                 │
│   CLI (Click)   VS Code Extension   REST API   Web Dashboard    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                       API GATEWAY                               │
│                                                                 │
│   FastAPI  ·  Auth/RBAC  ·  Rate Limiting  ·  API Keys         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      CORE SERVICES                              │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  DNA Engine  │  │  Analyzer    │  │  Memory Service      │  │
│  │              │  │              │  │                      │  │
│  │ - Extract    │  │ - AST parse  │  │ - Tasks              │  │
│  │ - Generate   │  │ - Deps       │  │ - Decisions          │  │
│  │ - .projectm  │  │ - Dead code  │  │ - Errors             │  │
│  │   ind/       │  │ - Security   │  │ - Patterns           │  │
│  └──────────────┘  │ - Dups       │  │ - Team memory        │  │
│                    └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Compression │  │  Prompt      │  │  Knowledge Graph     │  │
│  │  Engine      │  │  Engine      │  │                      │  │
│  │              │  │              │  │ - File → imports     │  │
│  │ - Budget     │  │ - Context    │  │ - Function → callers │  │
│  │ - Truncate   │  │ - Memories   │  │ - Impact analysis    │  │
│  │ - Assemble   │  │ - Template   │  │ - NetworkX / Neo4j   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Multi-Agent │  │  Review      │  │  Integrations        │  │
│  │  Orchestrator│  │  Engine      │  │                      │  │
│  │              │  │              │  │ - GitLab             │  │
│  │ - LangGraph  │  │ - RAG chain  │  │ - GitHub             │  │
│  │ - Specialist │  │ - MR comment │  │ - Slack / Jira       │  │
│  │   agents     │  │ - Two-stage  │  │ - Cursor / Windsurf  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      STORAGE LAYER                              │
│                                                                 │
│  SQLite / PostgreSQL  │  ChromaDB / LanceDB  │  Redis  │  Neo4j │
│  (structured memory)  │  (vector search)     │  (cache) │  (graph)│
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Init Flow (one-time per project)
```
projectmind init .
       │
       ▼
DNAExtractor           ← reads pyproject.toml, package.json, go.mod, etc.
       │
       ▼
DNAGenerator           ← writes .projectmind/*.md files
       │
       ▼
MemoryStore.init_db()  ← creates memory.db
       │
       ▼
.projectmind/ ready
```

### Agent Prompt Flow (every session)
```
Agent asks: "Add forgot password"
       │
       ▼
SmartPromptGenerator
  ├── Compressor.compress_with_budget()   ← reads .projectmind/*.md
  ├── MemoryStore.search("auth")          ← semantic search over memories
  └── assemble enriched prompt            ← 300–800 tokens, not 400k
       │
       ▼
Agent gets: framework + decisions + known bugs + style + relevant files
```

### Review Flow (every MR)
```
POST /review  (GitLab webhook or manual)
       │
       ▼
GitLabClient.get_diff()
       │
       ▼
RAG chain: diff + knowledge base + prompts
       │
       ▼
GitLabClient.write_comment()
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| FastAPI not Streamlit | API-first — works with CLI, VS Code, curl, agents |
| SQLite default, PostgreSQL optional | Zero-config local dev; swap to Postgres for teams |
| ChromaDB embedded | No external server required for vector search |
| NetworkX → optional Neo4j | Start simple; upgrade path when graph queries need scale |
| Character-based token estimation | No tokenizer dependency; accurate ±20% for all providers |
| LangChain LCEL | Composable chains; swap any LLM without touching pipeline logic |
| NVIDIA NIM via OpenAI client | Same API surface as OpenAI; 50+ models, one key |

---

## What's Built (Phase 1)

| Component | Location | Status |
|---|---|---|
| Project DNA Engine | `backend/core/dna/` | ✅ Complete |
| Architecture Analyzer | `backend/core/analyzer/` | ✅ Complete |
| Persistent Memory (SQLite) | `backend/core/memory/` | ✅ Complete |
| Vector Memory (ChromaDB) | `backend/core/memory/vector_store.py` | ✅ Complete |
| Token Compression Engine | `backend/core/compression/` | ✅ Complete |
| Smart Prompt Generator | `backend/core/prompt/` | ✅ Complete |
| FastAPI Backend | `backend/api/` | ✅ Complete |
| GitLab MR Reviewer | `backend/git/` + `/review` | ✅ Complete |
| CLI | `cli/main.py` | ✅ Complete |

## What's Next (Phase 2+)

| Feature | Phase | Complexity |
|---|---|---|
| Knowledge Graph | 2 | Medium |
| Multi-Agent System (LangGraph) | 3 | High |
| VS Code Extension | 4 | High |
| Auth + API Keys + Orgs | 5 | Medium |
| GitHub + Slack + Jira | 6 | Medium |
| AI Debate Mode | 7 | Medium |
| Team Memory + Attribution | 7 | Medium |
| AI Architect Advisor | 8 | High |
| PostgreSQL + Neo4j | 8 | Medium |
