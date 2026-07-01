from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.memory.store import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])

MEMORY_DB_FILENAME = ".projectmind/memory.db"


def _get_store(project_path: str, enable_vectors: bool = False) -> MemoryStore:
    db_path = Path(project_path) / MEMORY_DB_FILENAME
    if not db_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No memory.db found at {db_path}. Run `projectmind init` first.",
        )
    store = MemoryStore(str(db_path), enable_vectors=enable_vectors)
    store.init_db()
    return store


# ------------------------------------------------------------------
# Tasks
# ------------------------------------------------------------------

class AddTaskRequest(BaseModel):
    project_path: str
    name: str
    description: str
    files_changed: list[str] = []
    patterns: list[str] = []


class UpdateTaskRequest(BaseModel):
    project_path: str
    task_id: int
    status: str
    outcome_notes: Optional[str] = None


@router.get("/tasks")
def list_tasks(project_path: str):
    store = _get_store(project_path)
    tasks = store.list_tasks(project_path)
    return [t.model_dump() for t in tasks]


@router.post("/tasks")
def add_task(req: AddTaskRequest):
    store = _get_store(req.project_path, enable_vectors=True)
    task = store.add_task(
        project_path=req.project_path,
        name=req.name,
        description=req.description,
        files_changed=req.files_changed,
        patterns=req.patterns,
    )
    return task.model_dump()


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, req: UpdateTaskRequest):
    store = _get_store(req.project_path)
    task = store.update_task_status(task_id, req.status, req.outcome_notes)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.model_dump()


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------

class AddErrorRequest(BaseModel):
    project_path: str
    error: str
    fix: str
    confidence: float = 0.5


@router.get("/errors")
def list_errors(project_path: str):
    store = _get_store(project_path)
    return [e.model_dump() for e in store.list_errors(project_path)]


@router.post("/errors")
def add_error(req: AddErrorRequest):
    store = _get_store(req.project_path, enable_vectors=True)
    record = store.add_error(req.project_path, req.error, req.fix, req.confidence)
    return record.model_dump()


# ------------------------------------------------------------------
# Decisions
# ------------------------------------------------------------------

class AddDecisionRequest(BaseModel):
    project_path: str
    decision: str
    reason: str
    confidence: float = 0.8


@router.get("/decisions")
def list_decisions(project_path: str):
    store = _get_store(project_path)
    return [d.model_dump() for d in store.list_decisions(project_path)]


@router.post("/decisions")
def add_decision(req: AddDecisionRequest):
    store = _get_store(req.project_path, enable_vectors=True)
    record = store.add_decision(req.project_path, req.decision, req.reason, req.confidence)
    return record.model_dump()


# ------------------------------------------------------------------
# Patterns
# ------------------------------------------------------------------

class AddPatternRequest(BaseModel):
    project_path: str
    name: str
    description: str
    category: str
    example: Optional[str] = None
    confidence: float = 0.5


@router.get("/patterns")
def list_patterns(project_path: str):
    store = _get_store(project_path)
    return [p.model_dump() for p in store.list_patterns(project_path)]


@router.post("/patterns")
def add_pattern(req: AddPatternRequest):
    store = _get_store(req.project_path, enable_vectors=True)
    record = store.add_pattern(
        req.project_path, req.name, req.description,
        req.category, req.example, req.confidence,
    )
    return record.model_dump()


# ------------------------------------------------------------------
# Context summary (for token compression)
# ------------------------------------------------------------------

@router.get("/summary")
def memory_summary(project_path: str):
    store = _get_store(project_path)
    return store.get_context_summary(project_path)


@router.get("/search")
def search_memory(
    project_path: str,
    query: str,
    k: int = 6,
    types: Optional[str] = None,
):
    """Semantic search across memory types. `types` is a comma-separated filter, e.g. 'errors,decisions'."""
    store = _get_store(project_path, enable_vectors=True)
    memory_types = [t.strip() for t in types.split(",")] if types else None
    return store.search(query, k=k, memory_types=memory_types)
