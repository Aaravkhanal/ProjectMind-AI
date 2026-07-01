# Database Schema Map: ProjectMind AI

**19 tables across 6 domains · SQLite (`.projectmind/memory.db`)**

## Domain 1: Brain (5 tables)

### PRReview
Every code review run through the system.
```
id, project_path, platform, pr_number, pr_title, author
diff_size, files_changed, lines_added, lines_removed
task_complexity, models_used (JSON)
architect_score, security_score, quality_score, overall_score (0–10)
blocking_issues (JSON), suggestions (JSON)
estimated_cost_usd, duration_seconds
created_at
```

### FileHotspot
Per-file change signals derived from PR diffs.
```
id, project_path, file_path
change_count, bug_count, review_flags, debt_score (0–10)
last_changed
```

### Contributor
Per-author quality statistics, rolling averages.
```
id, project_path, author
pr_count, avg_diff_size
avg_quality_score, avg_security_score, blocking_issues_total
most_changed_files (JSON)
```

### TechDebt
Individual debt items extracted from review text.
```
id, project_path, pr_review_id (FK)
category (security|architecture|quality|testing|documentation)
severity (critical|high|medium|low)
description, file_path
resolved (bool), resolved_at
```

### ReviewInsight
Auto-generated aggregate insights, refreshed every 5 reviews.
```
id, project_path
insight_type (top_debt_files|debt_by_category|cost_trend|contributor_quality)
title, body, data_json
confidence (0–1), pr_count_basis
updated_at
```

---

## Domain 2: Memory (4 tables)

### Task
Work items tracked across sessions.
```
id, project_path, name, description
files_changed (JSON), patterns (JSON)
status, outcome_notes
created_at, updated_at
```

### ErrorMemory
Bugs seen and fixed — enables "have we seen this before?"
```
id, project_path, error_text, fix_text
confidence (0–1), occurrence_count, last_seen
```

### Decision
Architectural decisions with rationale.
```
id, project_path, decision_text, reason, outcome
confidence (0–1), superseded_by (self-FK)
created_at
```

### Pattern
Coding conventions and design patterns detected in the project.
```
id, project_path, name, description
category (coding_style|design_pattern|naming|structure)
example, confidence, occurrence_count
```

---

## Domain 3: Git Intelligence (3 tables)

### CommitRecord
Analyzed git commits.
```
id, project_path, commit_hash (unique), author, timestamp
message, commit_type (feature|bug_fix|refactor|test|docs|chore|revert|other)
is_merge (bool), files_changed, lines_added, lines_removed
```

### FileChurn
Per-file commit activity over rolling time windows.
```
id, project_path, file_path
commits_7d, commits_30d, commits_90d, commits_total
unique_authors, authors_json
bug_fix_commits, revert_commits
first_commit_at, last_commit_at
churn_score (0–10)
```

### PRRiskAssessment
Risk scores computed for a PR before it merges.
```
id, project_path, pr_title, pr_author, diff_size
overall_risk (0–10), risk_level (low|medium|high|critical)
breakdown_json (per-factor scores)
missing_tests (bool), recommendation
created_at
```

---

## Domain 4: Cost Management (3 tables)

### CostBudget
Per-project monthly budget configuration.
```
id, project_path (unique)
monthly_limit_usd, alert_at_percent (default 80)
hard_limit (bool), fallback_tier (fast|balanced|powerful|reasoning)
created_at, updated_at
```

### CostRecord
Per-operation cost tracking.
```
id, project_path, billing_month (YYYY-MM)
operation (review|plan|refactor|testing|docs|pipeline)
agent_role, provider, model_id, model_tier
tokens_input, tokens_output, tokens_total
estimated_cost_usd, actual_cost_usd, cost_source
was_downgraded (bool), original_model_id
duration_seconds, created_at
```

### CostAlert
Budget threshold events.
```
id, project_path
alert_type (threshold_60|threshold_80|threshold_100|hard_limit_hit)
message, spend_at_alert, budget_limit, percent_used
acknowledged (bool), created_at
```

---

## Domain 5: Execution Plans (2 tables)

### ExecutionPlan
Multi-step plans created from planner output.
```
id, project_path, title, goal, description
source (planner|manual|review)
status (draft→pending_approval→approved→in_progress→completed|cancelled)
total_steps, approved_steps, completed_steps
estimated_effort (XS|S|M|L|XL), estimated_cost_usd
created_by, approved_by
created_at, updated_at
```

### PlanStep
Individual steps within a plan.
```
id, plan_id (FK→ExecutionPlan), step_number
title, description, files (JSON)
effort (XS|S|M|L|XL), agent_type (planner|refactor|testing|docs)
requires_approval (bool)
status (pending→approved→in_progress→done|skipped|rejected)
approved_by, rejection_reason
started_at, completed_at
output, output_type (text|code|diff)
```

---

## Domain 6: Providers / BYOK (2 tables)

### ProviderKey
Encrypted API keys per project.
```
id, project_path, provider (openai|anthropic|google|groq|...)
encrypted_key (Fernet), base_url_override
is_active (bool)
health_status (ok|error|untested), health_message
last_tested_at, available_models_json
created_at, updated_at
```

### ModelProfile
Benchmark results per model per task type.
```
id, project_path, provider, model_id
score_code_review, score_architecture, score_security
score_documentation, score_bug_fix, score_testing
score_refactor, score_reasoning (all 0–10 or null)
avg_latency_ms, context_window
cost_per_1k_input, cost_per_1k_output
supports_tools, supports_vision, supports_streaming
created_at, updated_at
```

---

## Key Relationships
```
ExecutionPlan (1) ──── (N) PlanStep
PRReview     (1) ──── (N) TechDebt
CostRecord   (N) ──── CostBudget  (project-scoped)
CommitRecord (N) ──→  FileChurn   (analyzed into churn signals)
ReviewInsight (N) ←── PRReview + TechDebt (aggregated every 5 reviews)
ProviderKey  (1 per project/provider) → ModelProfile (N models)
```

## Indexing Strategy
All tables indexed on `project_path` (project-scoped queries).
Additional indexes: `commit_hash` (dedup), `billing_month` (cost aggregation),
`churn_score` (hotspot ranking), `created_at` (time series).
