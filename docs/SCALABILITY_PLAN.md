# Scalability Plan — ProjectMind AI

---

## Current Architecture Constraints

The Phase 1 system is deliberately simple:

| Component | Current | Constraint |
|---|---|---|
| Database | SQLite | Single writer, no horizontal scale |
| Vector store | ChromaDB embedded | Per-process, no shared access |
| API | Single FastAPI process | No worker pool |
| LLM calls | Synchronous | Blocks the HTTP thread |
| Storage | Local filesystem | Not accessible from multiple machines |

This is intentional — zero external dependencies makes local development instant. The upgrade path is clear and additive, not a rewrite.

---

## Scale-Up Progression

### Stage 1: Single Developer (Current)
```
Local machine
  └── projectmind CLI / FastAPI (1 process)
        ├── SQLite (.projectmind/memory.db)
        ├── ChromaDB (.projectmind/embeddings/)
        └── NVIDIA NIM / Ollama (external / local LLM)
```
Handles: 1 user, 1 project at a time. Latency: milliseconds (compression) to ~10s (LLM review).

---

### Stage 2: Small Team (5–20 developers)
```
Single server (4 cores, 8GB RAM)
  └── FastAPI + Uvicorn (4 workers via Gunicorn)
        ├── PostgreSQL (same server or managed RDS)
        ├── ChromaDB server (Docker, same machine)
        ├── Redis (session cache, rate limits)
        └── NVIDIA NIM API (external)
```

Changes needed:
- Swap SQLite → PostgreSQL (just change connection string in SQLModel)
- Switch ChromaDB embedded → ChromaDB HTTP client (change one line in `vector_store.py`)
- Add Gunicorn worker config
- Add Redis-based rate limiting middleware

Handles: 20 concurrent users, 50+ projects, ~100 reviews/day.

---

### Stage 3: Startup (50–500 developers)
```
Load balancer (nginx)
  ├── FastAPI pod × 3 (Kubernetes)
  │     ├── Async workers (anyio / ARQ for LLM jobs)
  │     └── Read replicas for /memory queries
  ├── PostgreSQL (primary + 1 read replica)
  ├── ChromaDB cluster (3 nodes)
  ├── Redis cluster
  └── Object storage (S3/R2) for report JSONs and embeddings
```

Changes needed:
- Move LLM calls to background job queue (ARQ or Celery)
- Add `GET /agents/task/{id}` polling endpoint for async results
- Store `.projectmind/` files in object storage, not local disk
- Add horizontal pod autoscaling on CPU/request-rate

Handles: 500 concurrent users, 1000+ projects, global teams.

---

### Stage 4: Enterprise / SaaS Scale
```
Multi-region deployment
  ├── API pods per region (us-east, eu-west, ap-southeast)
  ├── PostgreSQL (Aurora Serverless or PlanetScale)
  ├── Pinecone or Weaviate (managed vector DB, replaces ChromaDB)
  ├── Neo4j AuraDB (managed graph, replaces NetworkX)
  ├── CDN for static assets
  └── Kafka / SQS for event streaming (webhook triggers, audit logs)
```

---

## Performance Bottlenecks and Mitigations

### 1. LLM Call Latency (~5–15 seconds)
**Bottleneck:** `POST /review` and `--llm` enhanced flows block on network I/O.

**Mitigation:**
- Move all LLM calls to background queue (Phase 5)
- Return `{ task_id, status: "running" }` immediately
- Client polls `GET /agents/task/{id}` until complete
- Stream results via Server-Sent Events for real-time UX

### 2. Compression Is O(n) on File Count
**Bottleneck:** `ProjectParser.parse()` reads all Python files on every analysis.

**Mitigation:**
- Cache AST parse results keyed by `(file_path, mtime)`
- Re-parse only files that changed since last run (git diff)
- Store `last_analyzed_commit` in memory.db

### 3. ChromaDB Embedded — No Shared Access
**Bottleneck:** Multiple API workers can't share an embedded ChromaDB.

**Mitigation (Stage 2):**
- Switch to `chromadb.HttpClient(host, port)` — one line change
- Or migrate to LanceDB (faster for read-heavy workloads)

### 4. Knowledge Graph Build Time (Phase 2)
**Bottleneck:** Full graph build on a 10k-file repo takes seconds.

**Mitigation:**
- Build incrementally on git push (only process changed files)
- Cache serialized graph JSON; invalidate on next commit
- Use NetworkX for ≤5k nodes; offer Neo4j migration for larger

---

## Token Cost Projections

| Scenario | Without ProjectMind | With ProjectMind |
|---|---|---|
| Simple feature add | ~50k tokens (full context) | ~800 tokens (enriched prompt) |
| Architecture review | ~200k tokens | ~2k tokens (compressed + graph) |
| Bug fix with history | ~30k tokens | ~600 tokens (memory search) |
| MR code review | ~20k tokens | ~5k tokens (diff + RAG) |

**Savings:** 95–99% reduction in token consumption per agent session.
At $0.002/1k tokens (GPT-4o-mini), a team of 10 doing 20 tasks/day saves ~$40/day → ~$1,200/month.

---

## Infrastructure as Code

All production infra will be managed with:
- **Docker Compose** — local dev and small team (current)
- **Kubernetes Helm chart** — Stage 3+ (planned Phase 8)
- **Terraform** — cloud resources (planned Phase 8)

---

## Storage Upgrade Decision Matrix

| Need | Choice | When |
|---|---|---|
| Local dev | SQLite + ChromaDB embedded | Now (Phase 1) |
| Team sharing | PostgreSQL + ChromaDB HTTP | Phase 5 |
| High-scale vectors | Pinecone / Weaviate | Phase 8 |
| Complex graph queries | Neo4j AuraDB | Phase 7+ |
| Audit / event stream | Kafka / SQS | Phase 8 |
