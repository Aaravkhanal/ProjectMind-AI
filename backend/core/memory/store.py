"""
MemoryStore — unified interface for reading and writing all memory types.
Backed by SQLite (via SQLModel) with optional ChromaDB vector indexing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlmodel import Session, SQLModel, create_engine, select

from backend.core.memory.schema import Decision, ErrorMemory, Pattern, Task


class MemoryStore:
    def __init__(self, db_path: str, enable_vectors: bool = False):
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        self._vectors = None
        if enable_vectors:
            try:
                from backend.core.memory.vector_store import from_projectmind_dir
                pm_dir = Path(db_path).parent
                self._vectors = from_projectmind_dir(pm_dir)
            except Exception:
                pass  # vectors optional; store still works without them

    def init_db(self):
        SQLModel.metadata.create_all(self._engine)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def add_task(
        self,
        project_path: str,
        name: str,
        description: str,
        files_changed: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
    ) -> Task:
        task = Task(
            project_path=project_path,
            name=name,
            description=description,
            files_changed=json.dumps(files_changed or []),
            patterns=json.dumps(patterns or []),
        )
        with Session(self._engine) as session:
            session.add(task)
            session.commit()
            session.refresh(task)
        if self._vectors:
            try:
                self._vectors.embed_task(task)
            except Exception:
                pass
        return task

    def update_task_status(
        self,
        task_id: int,
        status: str,
        outcome_notes: Optional[str] = None,
    ) -> Optional[Task]:
        with Session(self._engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.status = status
                task.outcome_notes = outcome_notes
                task.updated_at = datetime.utcnow()
                session.add(task)
                session.commit()
                session.refresh(task)
            return task

    def list_tasks(self, project_path: str) -> List[Task]:
        with Session(self._engine) as session:
            return list(session.exec(select(Task).where(Task.project_path == project_path)))

    # ------------------------------------------------------------------
    # Error Memories
    # ------------------------------------------------------------------

    def add_error(
        self,
        project_path: str,
        error: str,
        fix: str,
        confidence: float = 0.5,
    ) -> ErrorMemory:
        with Session(self._engine) as session:
            existing = session.exec(
                select(ErrorMemory).where(
                    ErrorMemory.project_path == project_path,
                    ErrorMemory.error == error,
                )
            ).first()
            if existing:
                existing.occurrences += 1
                existing.fix = fix
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                existing.last_seen = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = ErrorMemory(
                project_path=project_path,
                error=error,
                fix=fix,
                confidence=confidence,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            if self._vectors:
                try:
                    self._vectors.embed_error(record)
                except Exception:
                    pass
            return record

    def list_errors(self, project_path: str) -> List[ErrorMemory]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(ErrorMemory)
                    .where(ErrorMemory.project_path == project_path)
                    .order_by(ErrorMemory.confidence.desc())  # type: ignore[arg-type]
                )
            )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def add_decision(
        self,
        project_path: str,
        decision: str,
        reason: str,
        confidence: float = 0.8,
    ) -> Decision:
        record = Decision(
            project_path=project_path,
            decision=decision,
            reason=reason,
            confidence=confidence,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        if self._vectors:
            try:
                self._vectors.embed_decision(record)
            except Exception:
                pass
        return record

    def list_decisions(self, project_path: str) -> List[Decision]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(Decision).where(Decision.project_path == project_path)
                )
            )

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def add_pattern(
        self,
        project_path: str,
        name: str,
        description: str,
        category: str,
        example: Optional[str] = None,
        confidence: float = 0.5,
    ) -> Pattern:
        with Session(self._engine) as session:
            existing = session.exec(
                select(Pattern).where(
                    Pattern.project_path == project_path,
                    Pattern.name == name,
                )
            ).first()
            if existing:
                existing.occurrence_count += 1
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                if example:
                    existing.example = example
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            record = Pattern(
                project_path=project_path,
                name=name,
                description=description,
                category=category,
                example=example,
                confidence=confidence,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            if self._vectors:
                try:
                    self._vectors.embed_pattern(record)
                except Exception:
                    pass
            return record

    def list_patterns(self, project_path: str) -> List[Pattern]:
        with Session(self._engine) as session:
            return list(
                session.exec(
                    select(Pattern).where(Pattern.project_path == project_path)
                )
            )

    # ------------------------------------------------------------------
    # Cross-type summary (for context compression)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Semantic search (delegates to VectorMemoryStore if enabled)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 6,
        memory_types: Optional[List[str]] = None,
    ) -> list:
        if self._vectors:
            results = self._vectors.search(query, k=k, memory_types=memory_types)
            return [
                {
                    "type": r.memory_type,
                    "content": r.content,
                    "score": round(r.score, 4),
                    "metadata": r.metadata,
                }
                for r in results
            ]
        # Fallback: keyword scan across SQLite records
        query_lower = query.lower()
        hits = []
        for project_path in self._all_project_paths():
            for e in self.list_errors(project_path):
                if query_lower in e.error.lower() or query_lower in e.fix.lower():
                    hits.append({"type": "error", "content": f"Error: {e.error}\nFix: {e.fix}", "score": 0.5})
            for d in self.list_decisions(project_path):
                if query_lower in d.decision.lower() or query_lower in d.reason.lower():
                    hits.append({"type": "decision", "content": f"Decision: {d.decision}\nReason: {d.reason}", "score": 0.5})
            for p in self.list_patterns(project_path):
                if query_lower in p.name.lower() or query_lower in p.description.lower():
                    hits.append({"type": "pattern", "content": f"Pattern: {p.name}\n{p.description}", "score": 0.5})
        return hits[:k]

    def _all_project_paths(self) -> List[str]:
        with Session(self._engine) as session:
            rows = session.exec(select(Task.project_path).distinct()).all()
            return list(rows)

    def get_context_summary(self, project_path: str) -> dict:
        return {
            "recent_tasks": [
                {
                    "name": t.name,
                    "status": t.status,
                    "files": json.loads(t.files_changed),
                }
                for t in self.list_tasks(project_path)[-10:]
            ],
            "known_errors": [
                {"error": e.error, "fix": e.fix, "confidence": e.confidence}
                for e in self.list_errors(project_path)
            ],
            "decisions": [
                {"decision": d.decision, "reason": d.reason}
                for d in self.list_decisions(project_path)
            ],
            "patterns": [
                {"name": p.name, "description": p.description, "category": p.category}
                for p in self.list_patterns(project_path)
            ],
        }
