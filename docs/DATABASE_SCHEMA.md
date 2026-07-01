# Database Schema — ProjectMind AI

---

## Current Schema (SQLite via SQLModel)

### `task`
Tracks every coding task an agent works on. Used to avoid repeating failed approaches.

```sql
CREATE TABLE task (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path    TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    files_changed   TEXT,          -- JSON array: ["src/auth.py", "src/models.py"]
    patterns        TEXT,          -- JSON array: ["JWT", "repository pattern"]
    status          TEXT DEFAULT 'pending',  -- pending | success | failure
    outcome_notes   TEXT,
    created_at      TEXT,
    updated_at      TEXT
);
CREATE INDEX idx_task_project ON task(project_path);
```

### `errormemory`
Records bugs, their root cause, and the fix. Future agents get warned before repeating them.

```sql
CREATE TABLE errormemory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path    TEXT NOT NULL,
    error           TEXT NOT NULL,   -- error description or stack trace excerpt
    fix             TEXT NOT NULL,   -- what resolved it
    confidence      REAL DEFAULT 0.5,  -- 0.0–1.0
    occurrences     INTEGER DEFAULT 1,
    last_seen       TEXT,
    created_at      TEXT
);
CREATE INDEX idx_error_project ON errormemory(project_path);
```

### `decision`
Architectural decisions with reasoning. Prevents re-litigating settled debates.

```sql
CREATE TABLE decision (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path    TEXT NOT NULL,
    decision        TEXT NOT NULL,   -- "Use JWT for auth"
    reason          TEXT NOT NULL,   -- "Stateless, microservice-compatible"
    outcome         TEXT,            -- "Worked well" / "Reversed in v2"
    confidence      REAL DEFAULT 0.8,
    superseded_by   INTEGER,         -- FK to another decision if overridden
    created_at      TEXT
);
```

### `pattern`
Reusable code patterns the project has established. Enforced in future generated code.

```sql
CREATE TABLE pattern (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path     TEXT NOT NULL,
    name             TEXT NOT NULL,   -- "Repository pattern"
    description      TEXT NOT NULL,
    category         TEXT,            -- "architecture" | "naming" | "testing" | "style"
    example          TEXT,            -- short code snippet
    confidence       REAL DEFAULT 0.5,
    occurrence_count INTEGER DEFAULT 1,
    created_at       TEXT
);
```

---

## Vector Collections (ChromaDB)

One Chroma collection per memory type per project. Collection name format: `{project_id}_{type}`.

| Collection | Embedded content | Metadata stored |
|---|---|---|
| `{pid}_tasks` | `name + description` | `task_id, status, created_at` |
| `{pid}_errors` | `error + fix` | `error_id, confidence, occurrences` |
| `{pid}_decisions` | `decision + reason` | `decision_id, confidence` |
| `{pid}_patterns` | `name + description + example` | `pattern_id, category, confidence` |

Project ID is derived from `hashlib.md5(project_path.encode()).hexdigest()[:8]`.

---

## Phase 5 Schema Additions (Multi-user)

### `organization`
```sql
CREATE TABLE organization (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    slug        TEXT NOT NULL UNIQUE,
    created_at  TEXT
);
```

### `user`
```sql
CREATE TABLE user (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id          INTEGER REFERENCES organization(id),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'member',  -- owner | admin | member | viewer
    created_at      TEXT
);
```

### `api_key`
```sql
CREATE TABLE api_key (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES user(id),
    key_hash    TEXT NOT NULL UNIQUE,   -- SHA-256 of the raw key
    name        TEXT NOT NULL,
    last_used   TEXT,
    expires_at  TEXT,
    created_at  TEXT
);
```

### `audit_log`
```sql
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES user(id),
    action      TEXT NOT NULL,    -- "init", "review", "memory.add_decision", etc.
    resource    TEXT,             -- project path or resource ID
    metadata    TEXT,             -- JSON
    created_at  TEXT
);
```

### `usage_metric`
```sql
CREATE TABLE usage_metric (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id          INTEGER REFERENCES organization(id),
    metric          TEXT NOT NULL,  -- "tokens_saved", "prompts_generated", "reviews_run"
    value           REAL NOT NULL,
    recorded_at     TEXT
);
```

---

## Phase 7 Schema Additions (Team Memory)

### `team_memory`
```sql
CREATE TABLE team_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path    TEXT NOT NULL,
    author          TEXT NOT NULL,    -- git username
    action          TEXT NOT NULL,    -- "added" | "removed" | "changed"
    subject         TEXT NOT NULL,    -- "Redis" | "AuthService" | "JWT"
    reason          TEXT,
    commit_hash     TEXT,
    files_affected  TEXT,             -- JSON array
    created_at      TEXT
);
```

### `prompt_memory`
```sql
CREATE TABLE prompt_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    task        TEXT NOT NULL,
    success     INTEGER,        -- 0 | 1
    quality     REAL,           -- 0.0–10.0, user-rated or LLM-rated
    tokens_used INTEGER,
    created_at  TEXT
);
```

---

## Storage Decision: SQLite → PostgreSQL

| Factor | SQLite | PostgreSQL |
|---|---|---|
| Setup | Zero — file on disk | Requires server |
| Concurrency | Single writer | Full concurrent writes |
| Use case | Solo dev, local | Teams, SaaS, high-volume |
| Migration | Alembic migration | Same Alembic migration |

The codebase uses SQLModel throughout, so swapping the connection string from `sqlite:///memory.db` to `postgresql://...` is the only change needed at the application level.
