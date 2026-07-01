# API Endpoint Map: ProjectMind AI

**90+ endpoints across 21 routers**

## Full Endpoint List

### Health (1)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status, version, uptime |

### Analysis (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/analyze` | Extract project DNA, initialize `.projectmind/` |

### Architecture (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/architecture` | AST analysis, dead code, duplicates, security scan |

### Graph (3)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/graph/build` | Build dependency knowledge graph |
| GET | `/graph` | Get graph JSON |
| GET | `/graph/impact` | Impact analysis: what breaks if file X changes? |

### Compression (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/compress` | Token-budget compression of project context |

### Memory (4)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/memory` | List all memory items |
| GET | `/memory/search` | Semantic search over memory |
| GET | `/memory/decisions` | Architectural decisions |
| GET | `/memory/errors` | Error memory (bugs seen before) |

### Prompt (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/prompt/generate` | Generate context-enriched agent prompt |

### Review (2)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/review` | GitLab MR review via RAG chain |
| POST | `/review/webhook` | GitLab webhook handler |

### Multi-Agent Review (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/review` | Parallel 3-agent review (architect + security + quality) |

### Advisor (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/advisor/ask` | Architectural Q&A from compressed project context |

### Dependencies (1)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/deps/risk` | Dependency CVEs, staleness, centrality scores |

### Onboarding (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/onboard/generate` | Role-aware reading list for new developers |

### ADR (3)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/adr` | List existing ADRs |
| POST | `/adr/detect` | Auto-detect ADR candidates from git history |
| POST | `/adr/create` | Generate MADR-format ADR |

### Tracer (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/tracer/trace` | Root cause analysis from error + memory + git |

### Explain (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/explain` | Generate ARCHITECTURE.md from real analysis data |

### GitHub App (1)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/github-app/webhook` | GitHub webhook: auto-review PRs, post comments |

### Models / Routing (5)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/models/available` | Models usable with current env keys |
| GET | `/models/catalog` | All 22 models across 5 providers |
| POST | `/models/recommend` | Classify task + recommend per-agent model |
| GET | `/models/routing-table` | Complexity → tier → model mapping |
| GET | `/models/providers` | Active vs inactive providers |

### Repository Brain (6)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/brain/summary` | Dashboard: reviews, hotspots, debt, contributors |
| GET | `/brain/hotspots` | Top files by change + debt score |
| GET | `/brain/contributors` | Author quality stats |
| GET | `/brain/debt` | Tech debt items by category/severity |
| GET | `/brain/insights` | Auto-generated insights |
| POST | `/brain/index` | Manual brain indexing trigger |

### Specialized Agents (5)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/plan` | Planner agent: goal → structured steps |
| POST | `/agents/refactor` | Refactor agent: before/after code |
| POST | `/agents/tests` | Testing agent: pytest test generation |
| POST | `/agents/docs` | Documentation agent: docstrings/README/API |
| POST | `/agents/pipeline` | All 4 specialized agents in parallel |

### Execution Plans (11)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/plans` | List execution plans |
| POST | `/plans` | Create plan (from planner output or manual) |
| GET | `/plans/{id}` | Get plan with all steps |
| DELETE | `/plans/{id}` | Cancel a plan |
| POST | `/plans/{id}/submit` | Submit plan for approval |
| POST | `/plans/{id}/approve` | Approve plan (unlocks steps) |
| GET | `/plans/{id}/steps` | List steps with status |
| POST | `/plans/{id}/steps/{sid}/approve` | Approve individual step |
| POST | `/plans/{id}/steps/{sid}/reject` | Reject step with reason |
| POST | `/plans/{id}/steps/{sid}/execute` | Run step via specialized agent |
| POST | `/plans/{id}/steps/{sid}/complete` | Mark step done manually |

### Git Intelligence (8)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/git-intel/analyze` | Analyze git history → classify commits + churn |
| GET | `/git-intel/summary` | Dashboard: commit types, risk, churn |
| GET | `/git-intel/commits` | Paginated commit history |
| GET | `/git-intel/churn` | File churn scores |
| POST | `/git-intel/co-changes` | Files that change together |
| POST | `/git-intel/score-risk` | Score PR risk from diff |
| GET | `/git-intel/risk-history` | Past risk assessments |
| POST | `/git-intel/classify-commit` | Classify commit message(s) |

### Cost Optimization (7)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/cost/summary` | Spend analytics, forecast, budget status |
| GET | `/cost/budget` | Current budget settings |
| POST | `/cost/budget` | Set/update project budget |
| GET | `/cost/history` | Per-operation cost records |
| GET | `/cost/alerts` | Unacknowledged budget alerts |
| POST | `/cost/alerts/acknowledge` | Clear alerts |
| POST | `/cost/optimize` | Dry-run: model selection with budget constraints |
| POST | `/cost/record` | Record cost entry manually |

### BYOK Providers (11)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/providers/catalog` | All 15+ supported providers |
| GET | `/providers` | Configured providers for project |
| POST | `/providers/add` | Add/update encrypted API key |
| DELETE | `/providers/{provider}` | Deactivate provider |
| POST | `/providers/{provider}/test` | Validate API key with real call |
| POST | `/providers/{provider}/benchmark` | Profile models (background) |
| GET | `/providers/recommendations` | Best/cheapest/fastest per task |
| POST | `/providers/complete` | Single LLM call via LiteLLM |
| POST | `/providers/debate` | Debate mode: N models → synthesis |
| POST | `/providers/vote` | Voting mode: majority answer |
| POST | `/providers/reflect` | Reflection mode: self-critique |

### Autonomous Code Editing (5)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/edit/plan` | Generate edit plan without applying |
| POST | `/edit/apply` | Apply a pre-approved plan |
| POST | `/edit/execute` | Plan + apply (autonomous) |
| POST | `/edit/rollback` | Undo via git stash pop |
| POST | `/edit/pipeline` | Sequential agent pipeline |
