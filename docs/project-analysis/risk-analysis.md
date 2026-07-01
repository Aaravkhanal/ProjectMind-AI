# Risk Analysis: BYOK Platform Upgrade

## Top 10 Risks

### 1. API Key Exposure (CRITICAL)
**Risk:** Encrypted keys in `secret.key` accessible if server compromised.
**Current mitigation:** Fernet encryption, `chmod 600`, `.gitignore` entry.
**Remaining gap:** Key rotation, audit trail, HSM not implemented.
**Action:** Add `POST /providers/{p}/rotate`, log all key access.

### 2. LiteLLM Provider Downtime Cascades (HIGH)
**Risk:** One provider API down → review fails with no fallback.
**Current mitigation:** `budget_per_task_usd` forces model downgrade, try/except in gateway.
**Remaining gap:** No circuit breaker, no explicit fallback chain config.
**Action:** Add `fallback_providers` list in ProviderKey, circuit breaker with 30s cooldown.

### 3. Cost Explosion from Reasoning Models (HIGH)
**Risk:** `o3-mini`, `DeepSeek R1`, `claude-opus-4-8` cost 10–100x; if budget check fails, one review could cost $10+.
**Current mitigation:** CostOptimizer checks remaining budget before each call.
**Remaining gap:** Cost estimate uses heuristics — actual litellm cost may differ.
**Action:** Use `litellm.completion_cost()` post-call; hard cap via `max_budget` in litellm.

### 4. Autonomous Edit Introduces Bugs (HIGH)
**Risk:** CodeEditorAgent generates valid Python but incorrect logic. Applied to production code.
**Current mitigation:** git stash rollback, `_BLOCKED_PATTERNS` protects secrets, Safe/Approval modes.
**Remaining gap:** No test runner integration before committing edits.
**Action:** Before marking autonomous edit done, run `pytest` (detect command, timeout 60s). Block apply if tests fail.

### 5. Debate Mode Response Parsing Failure (MEDIUM)
**Risk:** Synthesizer returns malformed structure → `final_answer` is garbage.
**Current mitigation:** Falls back to section after `## Final Synthesis` header, else uses full text.
**Remaining gap:** Winner detection is heuristic (substring match).
**Action:** Add structured output format (`json_mode=True` in litellm), retry once on parse failure.

### 6. Path Traversal in Code Editor (MEDIUM)
**Risk:** Malicious goal like "edit ../../etc/passwd" bypasses restrictions.
**Current mitigation:** `_safe_path()` resolves and checks path starts with project root.
**Remaining gap:** Symlink attacks could bypass prefix check.
**Action:** Add `os.path.realpath()` to `_safe_path()`, test with symlink fixtures.

### 7. Token Counting Inaccuracy (MEDIUM)
**Risk:** LiteLLM cost estimates don't match actual; monthly forecast skewed.
**Current mitigation:** `litellm.completion_cost()` post-call for accuracy.
**Remaining gap:** Some providers return 0 usage tokens (streaming, local models).
**Action:** Fall back to `tiktoken` estimate when usage is 0.

### 8. Secret Key File Loss (MEDIUM)
**Risk:** `.projectmind/secret.key` deleted → all stored API keys unrecoverable.
**Current mitigation:** None currently.
**Action:** Add `POST /providers/export` → encrypted key backup (requires master password).

### 9. LangGraph + LiteLLM Version Conflicts (LOW)
**Risk:** `langchain-core` version pinned by LangGraph conflicts with LiteLLM's requirements.
**Current mitigation:** LiteLLM is provider-agnostic, doesn't require LangChain.
**Remaining gap:** Both in same venv; pip may silently downgrade.
**Action:** Pin `langchain-core>=0.3.0,<0.4.0` in pyproject.toml, CI test on dependency install.

### 10. MCP Server Not Updated for New Endpoints (LOW)
**Risk:** Claude Code / Cursor users can't access BYOK, debate, edit features via MCP.
**Current mitigation:** REST API fully functional.
**Remaining gap:** MCP tools don't expose `/providers/*` or `/edit/*`.
**Action:** Add MCP tools: `byok_add_provider`, `run_debate`, `edit_code`, `rollback_edit`.

## Summary Matrix

| Risk | Severity | Likelihood | Current State | Priority |
|------|----------|------------|---------------|----------|
| API key exposure | Critical | Low | Mitigated | P1 |
| Provider downtime | High | Medium | Partial | P1 |
| Cost explosion | High | Medium | Mitigated | P1 |
| Autonomous edit bugs | High | Medium | Partial | P2 |
| Debate parse failure | Medium | Low | Mitigated | P3 |
| Path traversal | Medium | Very low | Mitigated | P2 |
| Token counting | Medium | Medium | Mitigated | P3 |
| Secret key loss | Medium | Low | Not mitigated | P2 |
| Dependency conflicts | Low | Low | Monitor | P4 |
| MCP not updated | Low | High | Known gap | P3 |
