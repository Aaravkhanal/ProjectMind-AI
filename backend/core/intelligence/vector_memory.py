"""
Phase 23 — Vector Memory System.

Persistent semantic memory backed by LanceDB (embedded, no server required).
Embeddings are generated via LiteLLM so any BYOK provider works.

Falls back gracefully if lancedb is not installed.

Embedding schema:
  id          — unique identifier (type:project:path or uuid)
  project     — project path
  type        — file | class | function | review | bug | decision |
                security | test | documentation | architecture | prompt
  path        — file or resource path
  content     — text to embed
  importance  — 0.0–1.0 (higher = retrieved first)
  agent       — which agent produced this memory
  timestamp   — ISO 8601
  vector      — float32[1536]
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_VECTOR_DIM = 1536  # OpenAI ada-002 / text-embedding-3-small default

try:
    import lancedb as _lancedb
    import pyarrow as _pa
    _LANCE_AVAILABLE = True
except ImportError:
    _lancedb = None  # type: ignore[assignment]
    _pa = None  # type: ignore[assignment]
    _LANCE_AVAILABLE = False


def _make_schema():
    if not _pa:
        return None
    return _pa.schema([
        _pa.field("id", _pa.string()),
        _pa.field("project", _pa.string()),
        _pa.field("type", _pa.string()),
        _pa.field("path", _pa.string()),
        _pa.field("content", _pa.string()),
        _pa.field("vector", _pa.list_(_pa.float32(), _VECTOR_DIM)),
        _pa.field("importance", _pa.float32()),
        _pa.field("agent", _pa.string()),
        _pa.field("timestamp", _pa.string()),
        _pa.field("metadata_json", _pa.string()),
    ])


class VectorMemory:
    def __init__(self, brain_dir: Path):
        self._db_path = str(brain_dir / "vectors")
        self._available = _LANCE_AVAILABLE
        self._db: Any = None
        self._table: Any = None

        if self._available:
            try:
                Path(self._db_path).mkdir(parents=True, exist_ok=True)
                self._db = _lancedb.connect(self._db_path)
                schema = _make_schema()
                self._table = self._db.create_table(
                    "embeddings", schema=schema, exist_ok=True
                )
            except Exception:
                self._available = False

    # ── public API ─────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    def embed(
        self,
        content: str,
        type: str,
        project: str,
        path: str = "",
        importance: float = 0.5,
        agent: str = "",
        metadata: Optional[dict] = None,
        record_id: Optional[str] = None,
        api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
    ) -> Optional[str]:
        if not self._available:
            return None

        vector = self._generate_embedding(content, embedding_model, api_key)
        if vector is None:
            return None

        doc_id = record_id or f"{type}:{project}:{path}:{uuid.uuid4().hex[:8]}"
        row = {
            "id": doc_id,
            "project": project,
            "type": type,
            "path": path,
            "content": content[:8000],
            "vector": vector,
            "importance": float(importance),
            "agent": agent,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata_json": json.dumps(metadata or {}),
        }
        try:
            self._table.add([row])
            return doc_id
        except Exception:
            return None

    def search(
        self,
        query: str,
        type_filter: Optional[str] = None,
        project: Optional[str] = None,
        k: int = 10,
        api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
    ) -> list[dict]:
        if not self._available:
            return []

        vector = self._generate_embedding(query, embedding_model, api_key)
        if vector is None:
            return self._keyword_search(query, type_filter, project, k)

        try:
            q = self._table.search(vector).limit(k)
            if type_filter:
                q = q.where(f"type = '{type_filter}'")
            if project:
                q = q.where(f"project = '{project}'")
            results = q.to_list()
            return [self._format_result(r) for r in results]
        except Exception:
            return self._keyword_search(query, type_filter, project, k)

    def search_similar_bugs(
        self,
        description: str,
        project: Optional[str] = None,
        k: int = 5,
        api_key: Optional[str] = None,
    ) -> list[dict]:
        return self.search(description, type_filter="bug", project=project, k=k, api_key=api_key)

    def search_similar_decisions(
        self,
        query: str,
        project: Optional[str] = None,
        k: int = 5,
        api_key: Optional[str] = None,
    ) -> list[dict]:
        return self.search(query, type_filter="decision", project=project, k=k, api_key=api_key)

    def search_similar_reviews(
        self,
        description: str,
        project: Optional[str] = None,
        k: int = 5,
        api_key: Optional[str] = None,
    ) -> list[dict]:
        return self.search(description, type_filter="review", project=project, k=k, api_key=api_key)

    def count(self, type_filter: Optional[str] = None) -> int:
        if not self._available:
            return 0
        try:
            if type_filter:
                return len(self._table.search().where(f"type = '{type_filter}'").limit(100000).to_list())
            return self._table.count_rows()
        except Exception:
            return 0

    def summary(self) -> dict:
        if not self._available:
            return {"available": False}
        try:
            total = self._table.count_rows()
            return {
                "available": True,
                "total_embeddings": total,
                "vector_dim": _VECTOR_DIM,
                "db_path": self._db_path,
            }
        except Exception:
            return {"available": True, "total_embeddings": 0}

    # ── internals ─────────────────────────────────────────────────────────────

    def _generate_embedding(
        self,
        text: str,
        model: str,
        api_key: Optional[str],
    ) -> Optional[list[float]]:
        try:
            import litellm
            kwargs: dict[str, Any] = {"model": model, "input": [text]}
            if api_key:
                kwargs["api_key"] = api_key
            response = litellm.embedding(**kwargs)
            return response.data[0]["embedding"]
        except Exception:
            return None

    def _keyword_search(
        self,
        query: str,
        type_filter: Optional[str],
        project: Optional[str],
        k: int,
    ) -> list[dict]:
        if not self._available:
            return []
        try:
            all_rows = self._table.search().limit(10000).to_list()
            q = query.lower()
            filtered = [
                r for r in all_rows
                if q in r.get("content", "").lower()
                and (not type_filter or r.get("type") == type_filter)
                and (not project or r.get("project") == project)
            ]
            filtered.sort(key=lambda r: r.get("importance", 0.0), reverse=True)
            return [self._format_result(r) for r in filtered[:k]]
        except Exception:
            return []

    def _format_result(self, r: dict) -> dict:
        return {
            "id": r.get("id"),
            "type": r.get("type"),
            "project": r.get("project"),
            "path": r.get("path"),
            "content": r.get("content", "")[:500],
            "importance": r.get("importance"),
            "agent": r.get("agent"),
            "timestamp": r.get("timestamp"),
            "score": r.get("_distance"),
            "metadata": json.loads(r.get("metadata_json", "{}")),
        }
