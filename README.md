# ProjectMind AI

**A production-grade BYOK Multi-Agent AI Engineering Platform built on top of your existing codebase.**

ProjectMind turns any project into an intelligent AI workspace. It automatically discovers what AI tools you already have, learns from your codebase over time, routes every task to the best available model, and lets multiple AI agents collaborate on your code — all without sending your API keys anywhere.

---

## What makes it different

Most AI coding tools are stateless. They forget everything between sessions, force you to pick models manually, and don't understand your project's history.

ProjectMind fixes all of that:

- **Zero setup** — detects your editor, API keys, local models, and MCP servers automatically on startup
- **BYOK** — your API keys stay on your machine, encrypted. The platform just orchestrates them
- **Learns over time** — every code review, every bug fix, every architectural decision gets stored in a persistent Repository Brain
- **Multi-agent by default** — architecture, security, and quality agents review code in parallel, then synthesize a single verdict
- **Routes intelligently** — automatically picks the best model for each task type based on what you actually have available
- **Works with any provider** — OpenAI, Anthropic, Google, Groq, DeepSeek, Mistral, Ollama, LM Studio, and 10+ more

---

## How it works

```
Your project
     │
     ▼
┌─────────────────────────────────────┐
│  Environment Discovery Engine       │  ← detects your IDE, API keys, local models, MCP servers
│  (Phase 20)                         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Repository Brain                   │  ← learns from every review: hotspots, debt, contributors
│  (SQLite persistent memory)         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Intelligent Model Router           │  ← picks best model per task, respects budget
│  + Cost Optimizer                   │
└──────────────┬──────────────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
 Architect  Security  Quality     ← 3 agents run in parallel via LangGraph
  Agent      Agent     Agent
     │         │         │
     └────┬────┘─────────┘
          ▼
    Synthesizer Agent              ← deduplicates + prioritizes findings
          │
          ▼
    Final Review + Brain Index     ← stores insights for future reviews
```

---

## Core features

### Environment-Aware Model Discovery
Automatically scans your machine on startup and detects:
- Which IDE you're using (Cursor, VS Code, Claude Code, Windsurf, Continue, Cline)
- Which API keys are configured in your environment
- Which local model servers are running (Ollama, LM Studio, vLLM, llama.cpp)
- Which MCP servers are configured
- Builds a capability matrix: best model for coding, security, docs, reasoning, etc.

### BYOK — Bring Your Own Keys
- Add API keys for any of 15+ providers via the API or VS Code extension
- Keys are encrypted with Fernet symmetric encryption and stored locally
- The platform never transmits your keys anywhere — all calls go directly from your machine to the provider
- Supports: OpenAI, Anthropic, Google, Groq, DeepSeek, OpenRouter, Together, Mistral, xAI, Fireworks, NVIDIA, HuggingFace, Ollama, LM Studio, vLLM

### Multi-Agent Code Review
Three specialized agents run in parallel on every review:
- **Architect Agent** — API design, layering, coupling, scalability patterns
- **Security Agent** — OWASP Top 10, secrets, auth flaws, injection risks (CRITICAL/HIGH/MEDIUM/LOW)
- **Quality Agent** — readability, error handling, test coverage, complexity
- **Synthesizer** — merges findings, removes duplicates, surfaces blocking issues first

### Repository Brain
Persistent learning that gets smarter with every review:
- Tracks which files change most and have the most bugs (hotspots)
- Identifies recurring tech debt by category
- Scores contributors by review quality
- Auto-generates architectural insights every 5 reviews
- Everything stored in SQLite — no external database needed

### Agent Orchestration Modes
Beyond standard review, run models in advanced collaboration modes:
- **Debate** — same question sent to N models, synthesizer scores each 1–10 and writes a combined answer
- **Voting** — N models answer, majority vote wins (best for factual/classification tasks)
- **Reflection** — model generates answer, critiques itself, produces improved version
- **Sequential Pipeline** — plan → refactor → test → docs, each stage feeds the next

### Autonomous Code Editing
Three safety levels for AI-generated file edits:
- **Safe mode** — generates a diff preview only, writes nothing
- **Approval mode** — creates an edit plan, waits for your approval
- **Autonomous mode** — applies changes directly with automatic git stash rollback if anything fails
- Blocks sensitive files (`.env`, secrets, keys, credentials) by pattern
- Path traversal protection built in

### Git Intelligence
- Classifies every commit by type (feature, fix, refactor, docs, chore) using Conventional Commits
- Scores file churn: which files change most and accumulate the most bugs
- PR risk scorer: 6-factor analysis (size, file types, test coverage, complexity, security, history)
- Co-change analysis: files that always change together (coupling signals)

### Cost Optimization Engine
- Tracks token usage and cost per operation, per agent, per model
- Monthly budget with configurable hard/soft limits
- Automatic model downgrade when budget is tight (stays in tier, picks cheaper model)
- Spend analytics: by operation, by tier, month-over-month comparison, 30-day forecast
- Budget alerts at 50%, 80%, 100% of monthly limit

### Model Capability Profiler
- Benchmarks any model across 8 task types using real prompts
- Scores code review, bug fixing, security analysis, testing, docs, reasoning, planning, refactoring
- Stores profiles in the database — recommendations get better over time
- Runs in the background so it never blocks your workflow

### Intelligent Task Router
- Classifies task complexity (SIMPLE / MEDIUM / COMPLEX) with no LLM call
- Maps each agent role to the right model tier (FAST / BALANCED / POWERFUL / REASONING)
- Budget-aware: downgrades model tier if estimated cost exceeds remaining budget
- Falls back to local Ollama models when no cloud key is available

### Observability
- Optional Langfuse integration: traces every agent call with tokens, cost, latency
- Set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` to activate — no code changes needed
- OpenTelemetry support for distributed tracing

---

## Architecture

```
llm-reviewer/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app, 93 endpoints across 21 routers
│   │   └── routes/              # One file per feature domain
│   │       ├── agents.py        # Multi-agent review
│   │       ├── brain.py         # Repository Brain
│   │       ├── cost.py          # Cost optimization
│   │       ├── discovery.py     # Environment discovery (Phase 20)
│   │       ├── git_intel.py     # Git intelligence
│   │       ├── providers.py     # BYOK provider management
│   │       ├── code_edit.py     # Autonomous code editing
│   │       └── ...              # 14 more route files
│   ├── agents/
│   │   ├── graph.py             # LangGraph multi-agent orchestration
│   │   ├── nodes.py             # Architect, Security, Quality, Synthesizer
│   │   ├── orchestration.py     # Debate, Vote, Reflect, Pipeline modes
│   │   ├── code_editor.py       # Autonomous file editing
│   │   └── specialized/         # Planner, Refactor, Testing, Docs, BugFix, Performance, DevOps
│   ├── core/
│   │   ├── brain/               # Repository Brain (indexer, schema, store)
│   │   ├── cost/                # Budget tracking, optimizer, alerts
│   │   ├── discovery/           # Environment scanner (OS, IDE, local, MCP)
│   │   ├── git_intel/           # Commit classifier, churn, risk scorer
│   │   ├── providers/           # BYOK key store, profiler, recommendations
│   │   └── observability/       # Langfuse tracer
│   ├── llm/
│   │   ├── litellm_gateway.py   # Universal LLM gateway (100+ providers)
│   │   ├── router.py            # Intelligent model router
│   │   └── providers.py         # Provider abstractions
│   └── mcp/
│       └── server.py            # MCP server (Claude Code, Cursor, Windsurf)
├── plugins/                     # Per-IDE discovery plugins
│   ├── base.py                  # DiscoveryPlugin base class
│   ├── cursor/                  # Cursor IDE plugin
│   ├── claude_code/             # Claude Code plugin
│   ├── continue_dev/            # Continue.dev plugin
│   ├── cline/                   # Cline plugin
│   ├── windsurf/                # Windsurf plugin
│   ├── vscode/                  # VS Code plugin
│   └── custom/                  # Custom endpoint registry
├── cli/
│   └── main.py                  # CLI: init, analyze, serve, generate-prompt
├── vscode-extension/            # VS Code extension v0.3.0
│   ├── src/
│   │   ├── extension.ts         # Entry point, 11 commands
│   │   ├── views/               # Brain, Git Intel, Cost, Plans sidebar views
│   │   └── projectmindClient.ts # API client
│   └── package.json
└── frontend/                    # Next.js dashboard
```

---

## Quick start

### Prerequisites
- Python 3.12+ with a virtual environment
- Node.js 18+ (for VS Code extension)

### 1. Clone and install

```bash
git clone https://github.com/Aaravkhanal/llm-reviewer
cd llm-reviewer
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env.local
```

Edit `.env.local` — at minimum set one provider:

```bash
# Option A: NVIDIA NIM (access to 50+ models with one key)
LLM_PROVIDER=nvidia
API_KEY=nvapi-your-key-here
API_URL=https://integrate.api.nvidia.com/v1

# Option B: OpenAI
LLM_PROVIDER=openai
API_KEY=sk-your-key-here

# Option C: No key — use Ollama (free, local)
LLM_PROVIDER=ollama
# Install Ollama from https://ollama.com then: ollama pull llama3.2
```

### 3. Start the backend

```bash
.venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Open the API explorer

```
http://localhost:8000/docs
```

Every endpoint is documented and testable from the browser.

### 5. Run your first scan

```
http://localhost:8000/discover/scan?project_path=.
```

This auto-detects your entire AI environment and builds a capability matrix in under 200ms.

---

## VS Code Extension

Install from the Marketplace: search **"ProjectMind AI"** in the Extensions panel, or:

```
https://marketplace.visualstudio.com/items?itemName=aaravkhanal.projectmind
```

### What the extension adds

**Activity Bar sidebar (4 panels):**
- **Repository Brain** — hotspots, tech debt, contributor scores
- **Git Intelligence** — commit type breakdown, churn, recent risk scores
- **Cost & Budget** — live spend tracking, budget alerts, model tier breakdown
- **Execution Plans** — AI-generated plans awaiting approval

**Commands (Cmd+Shift+P → "ProjectMind"):**

| Command | What it does |
|---------|-------------|
| Discover AI Environment | Scans your machine, shows routing table |
| Import Detected Providers | One-click import of env-var keys into encrypted store |
| Multi-Agent Review | Runs 3-agent parallel review on a diff |
| Generate Agent Prompt | Context-enriched prompt for any task |
| Score PR Risk | 6-factor risk assessment on a diff |
| Approve Plan | Review and approve AI execution plans |
| Set Monthly Budget | Configure spend limits |

### Extension settings

```json
{
  "projectmind.backendUrl": "http://localhost:8000",
  "projectmind.llmProvider": "nvidia",
  "projectmind.reviewBudgetUsd": 1.0
}
```

---

## API overview

93 endpoints across 21 domains. Full docs at `http://localhost:8000/docs`.

| Domain | Endpoints | Description |
|--------|-----------|-------------|
| `/discover/*` | 8 | Environment discovery, capability matrix, custom model registry |
| `/providers/*` | 11 | BYOK key management, debate, vote, reflect, benchmark |
| `/agents/*` | 6 | Multi-agent review, planner, refactor, tests, docs, pipeline |
| `/edit/*` | 5 | Autonomous code editing, rollback |
| `/brain/*` | 6 | Repository Brain: hotspots, debt, contributors, insights |
| `/git-intel/*` | 8 | Commit analysis, churn, risk scoring, co-changes |
| `/cost/*` | 8 | Budget, spend history, alerts, optimization |
| `/plans/*` | 11 | Execution plans with human-in-the-loop approval |
| `/models/*` | 5 | Model catalog, routing table, recommendations |
| Other | 25 | Health, analyze, graph, memory, prompt, review, ADR, tracer… |

---

## Supported providers

| Provider | Models | Type |
|----------|--------|------|
| Anthropic | Claude Opus 4.8, Sonnet 4.6, Haiku 4.5 | Cloud |
| OpenAI | GPT-4o, GPT-4o-mini, o3-mini | Cloud |
| Google | Gemini 2.5 Pro/Flash | Cloud |
| Groq | Llama 3.3-70B, 3.1-8B (fast inference) | Cloud |
| DeepSeek | DeepSeek V3, R1 Reasoner | Cloud |
| NVIDIA NIM | 50+ models via single API | Cloud |
| Mistral | Large, Small, Codestral | Cloud |
| xAI | Grok-3, Grok-3-mini | Cloud |
| OpenRouter | All models via proxy | Cloud |
| Together AI | Llama, Mixtral variants | Cloud |
| Ollama | Any model (llama3, qwen, phi, etc.) | Local (free) |
| LM Studio | Any GGUF model | Local (free) |
| vLLM | Self-hosted inference | Local (free) |
| llama.cpp | GGUF models | Local (free) |
| HuggingFace | Inference API | Cloud |

---

## Docker

```bash
docker compose up
```

API available at `http://localhost:8000`. All features work out of the box.

---

## Security

- API keys are encrypted with Fernet (AES-128-CBC) before storage
- Encryption key stored at `.projectmind/secret.key` (chmod 600, gitignored)
- `.env.local` is gitignored — never committed
- Autonomous code editor blocks `.env`, `*.key`, `*.pem`, `credentials`, `id_rsa` and other sensitive file patterns
- Path traversal protection on all file operations

---

## Built by

**Aarav Khanal** — [GitHub](https://github.com/Aaravkhanal)

VS Code Extension: [marketplace.visualstudio.com/items?itemName=aaravkhanal.projectmind](https://marketplace.visualstudio.com/items?itemName=aaravkhanal.projectmind)
