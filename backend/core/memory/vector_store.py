"""
VectorMemoryStore — embeds all memory types into per-project ChromaDB collections
and provides semantic search across them.

Collections per project:
  <prefix>_tasks       - task name + description embeddings
  <prefix>_errors      - error message embeddings
  <prefix>_decisions   - decision text embeddings
  <prefix>_patterns    - pattern name + description embeddings
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.core.memory.schema import Decision, ErrorMemory, Pattern, Task
from backend.vector.embeddings import Embeddings


@dataclass
class MemorySearchResult:
    memory_type: str      # "task" | "error" | "decision" | "pattern"
    content: str
    metadata: dict
    score: float = 0.0


class VectorMemoryStore:
    def __init__(self, embeddings_dir: str, project_id: str = "default"):
        """
        embeddings_dir: path to .projectmind/embeddings/
        project_id:     slug identifying the project (sanitised path or name)
        """
        self._dir = embeddings_dir
        self._pid = project_id.replace("/", "_").replace("\\", "_").strip("_")
        self._embedding = Embeddings.fast().embedding
        self._stores: dict[str, Chroma] = {}

    # ------------------------------------------------------------------
    # Internal store accessor — lazy-initialise each collection
    # ------------------------------------------------------------------

    def _store(self, collection: str) -> Chroma:
        key = f"{self._pid}_{collection}"
        if key not in self._stores:
            self._stores[key] = Chroma(
                persist_directory=self._dir,
                embedding_function=self._embedding,
                collection_name=key,
            )
        return self._stores[key]

    def _clear_cache(self):
        chromadb.api.client.SharedSystemClient.clear_system_cache()

    # ------------------------------------------------------------------
    # Embedding writers
    # ------------------------------------------------------------------

    def embed_task(self, task: Task) -> None:
        content = f"Task: {task.name}\n{task.description}\nStatus: {task.status}"
        doc = Document(
            page_content=content,
            metadata={
                "type": "task",
                "id": str(task.id),
                "name": task.name,
                "status": task.status,
            },
        )
        self._store("tasks").add_documents([doc])
        self._clear_cache()

    def embed_error(self, error: ErrorMemory) -> None:
        content = f"Error: {error.error}\nFix: {error.fix}"
        doc = Document(
            page_content=content,
            metadata={
                "type": "error",
                "id": str(error.id),
                "confidence": str(error.confidence),
            },
        )
        self._store("errors").add_documents([doc])
        self._clear_cache()

    def embed_decision(self, decision: Decision) -> None:
        content = f"Decision: {decision.decision}\nReason: {decision.reason}"
        doc = Document(
            page_content=content,
            metadata={
                "type": "decision",
                "id": str(decision.id),
                "confidence": str(decision.confidence),
            },
        )
        self._store("decisions").add_documents([doc])
        self._clear_cache()

    def embed_pattern(self, pattern: Pattern) -> None:
        content = f"Pattern [{pattern.category}]: {pattern.name}\n{pattern.description}"
        if pattern.example:
            content += f"\nExample: {pattern.example}"
        doc = Document(
            page_content=content,
            metadata={
                "type": "pattern",
                "id": str(pattern.id),
                "category": pattern.category,
            },
        )
        self._store("patterns").add_documents([doc])
        self._clear_cache()

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 6,
        memory_types: Optional[list[str]] = None,
    ) -> list[MemorySearchResult]:
        """
        Search across all (or specified) memory type collections.
        Returns up to `k` total results, distributed across types.
        """
        types = memory_types or ["tasks", "errors", "decisions", "patterns"]
        k_per = max(1, k // len(types))
        results: list[MemorySearchResult] = []

        for mem_type in types:
            try:
                store = self._store(mem_type)
                docs = store.similarity_search_with_relevance_scores(query, k=k_per)
                for doc, score in docs:
                    results.append(MemorySearchResult(
                        memory_type=mem_type.rstrip("s"),  # "tasks" → "task"
                        content=doc.page_content,
                        metadata=doc.metadata,
                        score=score,
                    ))
                self._clear_cache()
            except Exception:
                # Collection may be empty — skip silently
                pass

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def search_errors(self, query: str, k: int = 3) -> list[MemorySearchResult]:
        return self.search(query, k=k, memory_types=["errors"])

    def search_decisions(self, query: str, k: int = 3) -> list[MemorySearchResult]:
        return self.search(query, k=k, memory_types=["decisions"])

    def search_patterns(self, query: str, k: int = 3) -> list[MemorySearchResult]:
        return self.search(query, k=k, memory_types=["patterns"])


# ---------------------------------------------------------------------------
# Factory — instantiate from a project .projectmind/ directory
# ---------------------------------------------------------------------------

def from_projectmind_dir(pm_dir: str | Path) -> VectorMemoryStore:
    pm = Path(pm_dir)
    embeddings_dir = str(pm / "embeddings")
    Path(embeddings_dir).mkdir(parents=True, exist_ok=True)
    project_id = pm.parent.name  # use the project folder name
    return VectorMemoryStore(embeddings_dir=embeddings_dir, project_id=project_id)
