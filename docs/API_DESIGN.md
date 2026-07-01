# API Design — ProjectMind AI

Base URL: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

---

## Current Endpoints (Phase 1)

### Health

```
GET /health
→ { status: "ok", timestamp: "...", service: "ProjectMind AI" }
```

---

### Project Analysis

```
POST /analyze
Body: {
  project_path: string,
  enhance_with_llm: bool = false,
  llm_api_key?: string,
  llm_model?: string,
  llm_provider?: "openai" | "anthropic" | "nvidia" | "ollama"
}
→ {
  project_path: string,
  dna: { language, frameworks, architecture_pattern, database, ... },
  projectmind_dir: string,
  files_written: string[]
}
```

```
POST /architecture
Body: {
  project_path: string,
  max_files?: int = 500,
  save_report?: bool = true
}
→ {
  health_score: { overall, security, maintainability, ... },
  circular_dependencies: [...],
  dead_code: [...],
  duplicates: [...],
  security_issues: [...],
  report_path?: string
}

GET /architecture/report?project_path=...
→ ArchitectureReport JSON (cached)

GET /architecture/health?project_path=...
→ HealthScore JSON (cached)
```

---

### Memory

```
GET  /memory/tasks?project_path=...
POST /memory/tasks
Body: { project_path, name, description, files_changed?, patterns? }
→ Task

PATCH /memory/tasks/{task_id}
Body: { project_path, task_id, status, outcome_notes? }
→ Task

GET  /memory/errors?project_path=...
POST /memory/errors
Body: { project_path, error, fix, confidence? }
→ ErrorMemory

GET  /memory/decisions?project_path=...
POST /memory/decisions
Body: { project_path, decision, reason, confidence? }
→ Decision

GET  /memory/patterns?project_path=...
POST /memory/patterns
Body: { project_path, name, description, category, example?, confidence? }
→ Pattern

GET  /memory/summary?project_path=...
→ {
    recent_tasks: [...],
    known_errors: [...],
    decisions: [...],
    patterns: [...]
  }

GET  /memory/search?project_path=...&query=...&k=6&types=errors,decisions
→ [{ type, content, metadata, score }]
```

---

### Compression

```
POST /compress
Body: {
  project_path: string,
  with_budget?: bool = true,
  total_token_budget?: int = 6000
}
→ {
  project_path: string,
  context: { project, language, frameworks, ... },
  token_estimate: int,
  budget: { total_budget, used, remaining, utilisation_pct, slots: [...] },
  assembled_text: string
}
```

---

### Prompt Generation

```
POST /prompt/generate
Body: {
  project_path: string,
  task: string,
  llm_enhance?: bool = false,
  llm_model?: string,
  llm_provider?: string,
  api_key?: string,
  k_memories?: int = 5
}
→ {
  prompt: string,
  context: dict,
  relevant_memories: [...],
  budget: dict,
  token_estimate: int
}
```

---

### Code Review

```
POST /review
Body: {
  git_token: string,
  project_id: string,
  merge_request_iid: int,
  api_key?: string,
  llm_provider?: string = "openai",
  code_model?: string,
  conversation_model?: string,
  post_comment?: bool = true,
  knowledge_base_path?: string
}
→ {
  review: string,          -- formatted review
  posted: bool,            -- whether comment was posted to GitLab
  merge_request_iid: int
}
```

---

## Planned Endpoints (Phase 2+)

### Knowledge Graph (Phase 2)

```
POST /graph/build
Body: { project_path, max_files? }
→ { nodes: int, edges: int, graph_path: string }

GET /graph?project_path=...
→ { nodes: [...], edges: [...] }

GET /graph/impact?project_path=...&file=src/auth.py
→ {
    file: "src/auth.py",
    affected_files: [...],
    affected_functions: [...],
    depth: int
  }

GET /graph/dependencies?project_path=...&file=src/auth.py
→ { direct: [...], transitive: [...] }

GET /graph/central?project_path=...&top=10
→ [{ file, centrality_score, reason }]
```

---

### Multi-Agent (Phase 3)

```
POST /agents/run
Body: {
  project_path: string,
  task: string,
  agents: ["architect", "security", "reviewer"],  -- which agents to invoke
  diff?: string   -- optional code diff to review
}
→ {
  task_id: string,
  status: "running" | "complete",
  results: {
    architect?: string,
    security?: string,
    reviewer?: string,
    synthesis?: string
  }
}

GET /agents/task/{task_id}
→ task status + results (for async polling)
```

---

### Auth (Phase 5)

```
POST /auth/register
Body: { email, password, org_name }
→ { user_id, org_id, token }

POST /auth/login
Body: { email, password }
→ { token, expires_at }

POST /auth/api-keys
Body: { name, expires_in_days? }
→ { key: "pm_...", key_id, expires_at }  -- raw key shown once only

DELETE /auth/api-keys/{key_id}

GET /auth/usage
→ { tokens_saved, prompts_generated, reviews_run, ... }
```

---

## Authentication Scheme (Phase 5)

All endpoints (except `/health` and `/auth/*`) require one of:

```
Authorization: Bearer <jwt-token>
```
or
```
X-API-Key: pm_<key>
```

API keys are hashed (SHA-256) before storage. The raw key is shown only once at creation.

---

## Error Format

All errors follow RFC 7807:
```json
{
  "detail": "Human-readable message",
  "status": 422,
  "type": "validation_error"
}
```

---

## Rate Limits (Phase 5)

| Endpoint group | Free tier | Paid tier |
|---|---|---|
| `/analyze` | 10/day | 200/day |
| `/review` | 5/day | unlimited |
| `/prompt/generate` | 50/day | unlimited |
| `/memory/*` | 200/day | unlimited |
| `/agents/run` | 2/day | 50/day |
