# Components — ProjectMind AI

All components that exist today plus their design rationale and extension points.

---

## Backend Components

### `backend/core/dna/`
**What:** Extracts and generates the "DNA" of a project — its language, frameworks, architecture, DB, auth, deployment, etc.

**Files:**
- `extractor.py` — `DNAExtractor` reads config files, folder structure, git remote; returns `ProjectDNA` dataclass
- `generator.py` — `DNAGenerator` writes `.projectmind/*.md` files from a `ProjectDNA`

**How it works:**
1. Detects language by looking for `pyproject.toml` (Python), `package.json+tsconfig.json` (TypeScript), `go.mod` (Go), `Cargo.toml` (Rust)
2. Detects frameworks via keyword signals in dep files (e.g. `fastapi` → FastAPI, `react` → React)
3. Detects architecture by mapping folder names to patterns (e.g. `services/` + `repositories/` → service-repository)
4. Writes human-readable `.md` files that the Compressor can parse later

**Extension points:** Add new language detectors in `LANGUAGE_SIGNALS`, new framework signals in `FRAMEWORK_SIGNALS`, new architecture patterns in `ARCH_PATTERNS`.

---

### `backend/core/analyzer/`
**What:** Static analysis engine — no external tools, pure Python AST.

**Files:**
- `ast_parser.py` — `ProjectParser` walks Python files, extracts `FunctionInfo`, `ClassInfo`, `ImportInfo`; calculates cyclomatic complexity
- `dependency.py` — `DependencyAnalyzer` builds import graph, finds circular dependencies (DFS with WHITE/GRAY/BLACK coloring), finds unused imports
- `duplicates.py` — `DuplicateDetector` groups functions by MD5 hash of their AST body
- `dead_code.py` — `DeadCodeDetector` cross-references all defined names against all used names across the project
- `security.py` — `SecurityScanner` runs 23 regex rules + AST rules; covers eval/exec injection, pickle, hardcoded secrets, weak crypto, path traversal
- `reporter.py` — `Reporter` assembles all results into `ArchitectureReport` with health score; saves JSON to `.projectmind/`

**Health score formula:**
```
health = 10.0
- (circular_deps * 0.5)
- (dead_functions * 0.1)
- (duplicate_groups * 0.2)
- (security_errors * 1.0)
- (security_warnings * 0.3)
```
Clamped to [0, 10].

**Extension points:** Add rules to `_COMPILED_RULES` in `security.py`. Add new smell detectors as separate classes following the `detect() → Report` pattern.

---

### `backend/core/memory/`
**What:** Persistent project memory across sessions.

**Files:**
- `schema.py` — SQLModel table definitions: `Task`, `ErrorMemory`, `Decision`, `Pattern`
- `store.py` — `MemoryStore` CRUD + semantic search. Vector embedding is opt-in (`enable_vectors=True`)
- `vector_store.py` — `VectorMemoryStore` wraps ChromaDB; one collection per memory type per project

**Storage:**
- SQLite at `.projectmind/memory.db` (default)
- ChromaDB at `.projectmind/embeddings/` (created on first vector operation)

**Extension points:** Add new memory types by adding a SQLModel table in `schema.py` and corresponding `add_*/list_*` methods in `store.py`. Add a new ChromaDB collection in `vector_store.py`.

---

### `backend/core/compression/`
**What:** Converts `.projectmind/*.md` files into a token-efficient JSON context — without calling an LLM.

**Files:**
- `budget.py` — `TokenBudget` with named priority slots. `coding_agent_budget(6000)` and `review_agent_budget(4000)` pre-configured
- `compressor.py` — `Compressor` reads the `.md` files, parses sections, fills budget slots

**Token estimation:** `len(text) // 4` — works within ±20% for all major providers (OpenAI, Anthropic, Llama).

**Extension points:** Add new budget profiles (e.g. `documentation_budget()`). Add new `.md` file parsers for custom sections.

---

### `backend/core/prompt/`
**What:** Generates context-enriched prompts for coding agents.

**Files:**
- `generator.py` — `SmartPromptGenerator` combines compressed context + semantic memory search + task description → structured prompt

**Template used:**
```
# Coding Task — Context-Enriched Prompt
## Project Context (framework, DB, auth, architecture)
## Coding Conventions
## Architectural Decisions (must follow)
## Known Pitfalls (avoid these)
## Relevant Patterns
## Recent Task History
## Task
```

**Extension points:** Modify `PROMPT_TEMPLATE` in `generator.py`. Add LLM enhancement via `SMART_PROMPT` prompt template.

---

### `backend/llm/`
**What:** Provider-agnostic LLM abstraction.

**Files:**
- `providers.py` — `LLM` class supporting NVIDIA NIM, OpenAI, Anthropic, Ollama via `LLMProvider` enum. `LLM.load_prompt()` reads `.md` prompt templates.
- `prompts/` — Markdown prompt templates: `context.md`, `response.md`, `dna_extract.md`, `smart_prompt.md`, `compress.md`

**Extension points:** Add a new provider by adding an enum value and a branch in `LLM._load()`.

---

### `backend/vector/`
**What:** ChromaDB vector store wrapper for the RAG review pipeline (separate from the memory vector store).

**Files:**
- `embeddings.py` — `Embeddings` with `default()` (all-mpnet-base-v2) and `fast()` (all-MiniLM-L6-v2) classmethods
- `store.py` — `VectorStore` with `load()`, `add_documents()`, `search()`, `as_retriever()`

---

### `backend/git/`
**What:** GitLab API client.

**Files:**
- `gitlab.py` — `GitLabClient` with `get_diff()` and `write_comment()`. Comment is updated in-place if a prior review exists (identified by "Code Review Documentation" heading).

**Extension points:** Port `get_diff()` and `write_comment()` for GitHub by adding `github.py` with the same interface.

---

### `backend/api/`
**What:** FastAPI application wiring all core services into HTTP endpoints.

**Routes:**
| Router | Prefix | Description |
|---|---|---|
| `health.py` | `/health` | Liveness check |
| `analyze.py` | `/analyze` | DNA extraction + init |
| `architecture.py` | `/architecture` | Static analysis |
| `compress.py` | `/compress` | Token compression |
| `memory.py` | `/memory` | CRUD + search |
| `prompt.py` | `/prompt` | Prompt generation |
| `review.py` | `/review` | MR code review |

---

### `cli/main.py`
**What:** Click CLI exposing all core features without starting the API server.

**Commands:**
- `init` — DNA extraction + `.projectmind/` generation
- `analyze` — static analysis report
- `compress` — token-efficient context JSON
- `generate-prompt` — enriched agent prompt
- `memory list/add-decision/add-error/search`
- `serve` — start FastAPI backend

---

## Storage Components

| Store | Purpose | Location |
|---|---|---|
| SQLite | Structured memory (tasks, decisions, errors, patterns) | `.projectmind/memory.db` |
| ChromaDB | Vector embeddings for semantic search | `.projectmind/embeddings/` |
| Markdown files | Human-readable project knowledge | `.projectmind/*.md` |
| JSON files | Machine-readable reports | `.projectmind/architecture_report.json` |
| Redis | Session cache (optional, only for high-volume API) | External, Docker |

---

## Upcoming Components (Phase 2+)

| Component | Location | Purpose |
|---|---|---|
| Knowledge Graph | `backend/core/graph/` | File/function relationship graph |
| Multi-Agent Orchestrator | `backend/core/agents/` | LangGraph specialist agents |
| Auth Middleware | `backend/api/middleware/` | JWT + API key validation |
| Team Memory | `backend/core/memory/team.py` | Per-author decision attribution |
| GitHub Client | `backend/git/github.py` | GitHub PR reviewer |
| VS Code Extension | `vscode-extension/` | TypeScript editor integration |
