# Agent Map: ProjectMind AI

## Review Agents (LangGraph)

```
START
  │
  ▼
dispatcher_node
  │  - Classifies task complexity (SIMPLE/MEDIUM/COMPLEX)
  │  - Routes each agent to appropriate model tier via ModelRouter
  │  - Runs 3 agents in parallel (ThreadPoolExecutor, max_workers=3, timeout=180s)
  │
  ├──────────────────────────────────┐
  │                                  │
  ▼                                  ▼                    ▼
architect_node              security_node         quality_node
  │                                  │                    │
  │ Model: POWERFUL tier             │ Model: REASONING   │ Model: BALANCED
  │ Focus: API design,               │ Focus: OWASP Top10 │ Focus: readability,
  │  layering, coupling,             │  secrets, auth,    │  error handling,
  │  dependency creep,               │  validation,       │  test coverage,
  │  scalability patterns            │  CRITICAL/HIGH/    │  complexity
  │                                  │  MEDIUM/LOW flags  │
  └──────────────┬───────────────────┘────────────────────┘
                 │
                 ▼
         synthesizer_node
           │ Model: BALANCED tier
           │ - De-duplicates findings across 3 agents
           │ - Prioritizes BLOCKING issues first
           │ - Produces unified review <600 words
           │ - Fallback: concatenates if LLM fails
                 │
                 ▼
               END
```

## Specialized Agents (LCEL Chains)

| Agent | Tier | Input | Output |
|-------|------|-------|--------|
| **PlannerAgent** | BALANCED | code + goal + context | Markdown: Goal / Steps (with files+effort) / Risks / Done |
| **RefactorAgent** | POWERFUL | code + description | Before/After blocks marked [SAFE]/[NEEDS_TESTS]/[RISKY] |
| **TestingAgent** | BALANCED | code + framework | pytest by default; `extra.test_framework` overrides |
| **DocsAgent** | FAST | code + doc_type | Docstrings / README section / API docs (3 modes) |
| **BugFixAgent** | BALANCED | code + error_text | Root cause / Fixed code / Explanation / Prevention |
| **PerformanceAgent** | POWERFUL | code | Complexity issues / Memory issues / I/O bottlenecks / Optimized version |
| **DevOpsAgent** | BALANCED | dockerfile/ci/k8s | Security / Best practices / Reliability / Improved config |

## Orchestration Modes

### Debate Mode (`/providers/debate`)
```
Same question ──┬──→ Model A ──┐
                ├──→ Model B ──┼──→ Synthesizer ──→ Scored summary + winner + synthesis
                └──→ Model C ──┘
```
- All 3 models run in parallel
- Synthesizer scores each 1–10 on accuracy/depth/clarity/actionability
- Final answer = combined best insights

### Voting Mode (`/providers/vote`)
```
Same question ──┬──→ Model A (answer)
                ├──→ Model B (answer)  ──→ Counter.most_common() ──→ winner
                └──→ Model C (answer)
```
- Best for factual / classification tasks
- Returns majority answer + all responses

### Reflection Mode (`/providers/reflect`)
```
question ──→ Model (initial) ──→ critique prompt ──→ Model (improved) ──→ ...N rounds
```
- Single model, N critique rounds (default 1)
- Each round: "what was wrong? write improved version"
- Returns final improved answer + all rounds

### Sequential Pipeline (`/edit/pipeline`)
```
code ──→ Planner ──→ Refactor ──→ Testing ──→ Docs
          output feeds as context into each next stage
```
- Each stage receives prior stage output as context
- Customizable stage list
- Returns per-stage output + total cost

## Model Router Logic

```python
task_complexity = classify_task(description, diff, file_count)
# → SIMPLE | MEDIUM | COMPLEX (no LLM call, pure heuristics)

agent_tier = _AGENT_TIER[agent_role]
# architect → POWERFUL, security → REASONING, quality → BALANCED

allowed_tiers = _COMPLEXITY_TO_TIERS[complexity]
# SIMPLE → [FAST, BALANCED], MEDIUM → [BALANCED, POWERFUL], COMPLEX → [POWERFUL, REASONING]

candidate_tiers = intersection(agent_tier, allowed_tiers)
# Pick models from candidate tiers, filtered by provider availability

budget_check()  # downgrade tier if estimated_cost > remaining_budget

return best_model, estimated_cost_usd, reason
```

## CodeEditorAgent

```
goal + target_files
        │
        ▼
   LLM (JSON edit plan)
        │
        ▼
   Parse FileChange[]  {action, path, content, reason}
        │
   ┌────┴────────────────────────────┐
   │ mode == "safe"                  │ return diff_preview (no writes)
   │ mode == "approval"              │ return plan for human to call /edit/apply
   │ mode == "autonomous"            │ git stash → apply changes → report
   └─────────────────────────────────┘
        │
        ▼ (autonomous only)
   Path safety check (_safe_path)
   Secret file blocking (_BLOCKED_PATTERNS)
   Write / Create / Delete / Rename
        │
        ▼
   Return EditResult {applied, changes, errors, rollback_available}
```
