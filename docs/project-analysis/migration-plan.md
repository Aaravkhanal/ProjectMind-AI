# Migration Plan: LLM Reviewer → BYOK Multi-Agent Platform

## What's Already Done (v0.2 → now)
All items below were implemented in this update — no migration needed.

| Component | Status | Location |
|-----------|--------|----------|
| LiteLLM gateway | ✅ | `backend/llm/litellm_gateway.py` |
| Encrypted BYOK key storage | ✅ | `backend/core/providers/schema.py` + `store.py` |
| Provider management API | ✅ | `backend/api/routes/providers.py` |
| Model profiling/benchmarking | ✅ | `backend/core/providers/profiler.py` |
| Bug Fix agent | ✅ | `backend/agents/specialized/bugfix.py` |
| Performance agent | ✅ | `backend/agents/specialized/performance.py` |
| DevOps agent | ✅ | `backend/agents/specialized/devops.py` |
| Debate mode | ✅ | `backend/agents/orchestration.py` + `/providers/debate` |
| Voting mode | ✅ | `backend/agents/orchestration.py` + `/providers/vote` |
| Reflection mode | ✅ | `backend/agents/orchestration.py` + `/providers/reflect` |
| Sequential pipeline | ✅ | `backend/agents/orchestration.py` + `/edit/pipeline` |
| Autonomous code editing | ✅ | `backend/agents/code_editor.py` + `/edit/*` |
| Langfuse observability | ✅ | `backend/core/observability/langfuse_tracker.py` |
| Architecture docs (9 files) | ✅ | `docs/project-analysis/` |

## Next Migration Steps (v0.3)

### Step 1: Wire LiteLLM into existing ModelRouter (2 days)
Currently `ModelRouter` calls LangChain providers directly.
Migrate internal calls to use `LiteLLMGateway.complete()` as the backend.
Preserves all routing logic, just changes the execution layer.

```python
# Before (nodes.py)
llm = ChatOpenAI(model=model_id, api_key=key)
chain = prompt | llm | StrOutputParser()

# After
response = gateway.complete(model=model_id, messages=[...])
```

### Step 2: Add BYOK key resolution to ModelRouter (1 day)
Update `ModelRouter._available_models()` to check `ProviderStore` for
active keys in addition to environment variables.

### Step 3: Auto-trigger profiling on key add (1 day)
In `/providers/add`, auto-start benchmark in background if `auto_profile=true`.
This populates the recommendations table immediately.

### Step 4: Langfuse integration into agent calls (2 days)
Wrap `dispatcher_node` and specialized agent `run()` calls with `Tracer` spans.
Each agent call records model, tokens, cost, latency.

### Step 5: API key rotation (3 days)
Add `POST /providers/{provider}/rotate` — generate new key, verify it works,
swap encrypted value, invalidate old key. Audit log entry per rotation.

## v0.4 Roadmap (Enterprise)

### Multi-tenancy
- Add `tenant_id` to all 19 tables (nullable first, then migrate)
- Middleware: resolve tenant from JWT or API key header
- Per-tenant: budgets, provider keys, brain data, execution plans

### RBAC
- Tables: `Tenant`, `TeamMember` (tenant_id, user_id, role)
- Roles: owner / admin / reviewer / viewer
- Middleware enforcement on all write endpoints

### PostgreSQL option
- Extract `create_engine()` to a factory function
- Read `DATABASE_URL` env var: `sqlite:///...` or `postgresql://...`
- No schema changes needed (SQLModel is DB-agnostic)

### Audit logs
- New `AuditLog` table: tenant_id, user_id, action, resource, timestamp
- Middleware: log all POST/PUT/DELETE automatically

## Breaking Change Risk
| Change | Risk | Mitigation |
|--------|------|------------|
| LiteLLM replacing direct LangChain calls | LOW | Same interface, transparent swap |
| New DB tables (ProviderKey, ModelProfile) | NONE | New tables, no existing table changes |
| `/providers/*` routes | NONE | New routes, no conflicts |
| `/edit/*` routes | NONE | New routes, no conflicts |
| `cryptography` key file | LOW | Auto-created on first use |
