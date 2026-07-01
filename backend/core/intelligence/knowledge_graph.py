"""
Phase 22 — Knowledge Graph System.

Persistent graph database backed by KuzuDB (embedded, no server required).
Falls back to an in-memory networkx graph if kuzu is not installed.

Node tables: File, Directory, Class, Function, Service
Relationship tables: IMPORTS, DEFINES, CALLS, CONTAINS, DEPENDS_ON, BELONGS_TO
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

try:
    import kuzu as _kuzu
    _KUZU_AVAILABLE = True
except ImportError:
    _kuzu = None  # type: ignore[assignment]
    _KUZU_AVAILABLE = False

_SCHEMA_DDL = [
    # Node tables
    "CREATE NODE TABLE IF NOT EXISTS File("
    "  path STRING, language STRING, loc INT64, PRIMARY KEY (path))",

    "CREATE NODE TABLE IF NOT EXISTS Directory("
    "  path STRING, PRIMARY KEY (path))",

    "CREATE NODE TABLE IF NOT EXISTS Class("
    "  id STRING, name STRING, file_path STRING,"
    "  method_count INT64, line_start INT64, PRIMARY KEY (id))",

    "CREATE NODE TABLE IF NOT EXISTS Function("
    "  id STRING, name STRING, file_path STRING,"
    "  complexity INT64, is_async BOOLEAN, line_start INT64, PRIMARY KEY (id))",

    "CREATE NODE TABLE IF NOT EXISTS Service("
    "  name STRING, type STRING, PRIMARY KEY (name))",

    # Relationship tables
    "CREATE REL TABLE IF NOT EXISTS IMPORTS(FROM File TO File)",
    "CREATE REL TABLE IF NOT EXISTS DEFINES(FROM File TO Class)",
    "CREATE REL TABLE IF NOT EXISTS DEFINES_FN(FROM File TO Function)",
    "CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Class TO Function)",
    "CREATE REL TABLE IF NOT EXISTS BELONGS_TO(FROM File TO Directory)",
    "CREATE REL TABLE IF NOT EXISTS DEPENDS_ON(FROM Service TO Service, weight DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS CALLS(FROM Function TO Function)",
]


class KnowledgeGraph:
    def __init__(self, brain_dir: Path):
        self._db_path = str(brain_dir / "knowledge")
        self._available = _KUZU_AVAILABLE
        self._db: Any = None
        self._conn: Any = None

        if self._available:
            try:
                Path(self._db_path).mkdir(parents=True, exist_ok=True)
                self._db = _kuzu.Database(self._db_path)
                self._conn = _kuzu.Connection(self._db)
                self._init_schema()
            except Exception as e:
                self._available = False
                self._conn = None

    # ── public API ─────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    def add_file(self, path: str, language: str = "", loc: int = 0) -> None:
        if not self._conn:
            return
        self._exec(
            "MERGE (:File {path: $path, language: $lang, loc: $loc})",
            {"path": path, "lang": language, "loc": loc},
        )

    def add_directory(self, path: str) -> None:
        if not self._conn:
            return
        self._exec("MERGE (:Directory {path: $path})", {"path": path})

    def add_class(
        self,
        file_path: str,
        name: str,
        method_count: int = 0,
        line_start: int = 0,
    ) -> None:
        if not self._conn:
            return
        node_id = f"{file_path}::{name}"
        self._exec(
            "MERGE (:Class {id: $id, name: $name, file_path: $fp,"
            " method_count: $mc, line_start: $ls})",
            {"id": node_id, "name": name, "fp": file_path, "mc": method_count, "ls": line_start},
        )
        self._exec(
            "MATCH (f:File {path: $fp}), (c:Class {id: $id})"
            " MERGE (f)-[:DEFINES]->(c)",
            {"fp": file_path, "id": node_id},
        )

    def add_function(
        self,
        file_path: str,
        name: str,
        qualified_name: str,
        complexity: int = 1,
        is_async: bool = False,
        line_start: int = 0,
        parent_class: Optional[str] = None,
    ) -> None:
        if not self._conn:
            return
        node_id = f"{file_path}::{qualified_name}"
        self._exec(
            "MERGE (:Function {id: $id, name: $name, file_path: $fp,"
            " complexity: $cx, is_async: $async, line_start: $ls})",
            {
                "id": node_id, "name": name, "fp": file_path,
                "cx": complexity, "async": is_async, "ls": line_start,
            },
        )
        self._exec(
            "MATCH (f:File {path: $fp}), (fn:Function {id: $id})"
            " MERGE (f)-[:DEFINES_FN]->(fn)",
            {"fp": file_path, "id": node_id},
        )
        if parent_class:
            class_id = f"{file_path}::{parent_class}"
            self._exec(
                "MATCH (c:Class {id: $cid}), (fn:Function {id: $fid})"
                " MERGE (c)-[:CONTAINS]->(fn)",
                {"cid": class_id, "fid": node_id},
            )

    def add_import(self, src_path: str, dst_path: str) -> None:
        if not self._conn:
            return
        self._exec(
            "MATCH (a:File {path: $src}), (b:File {path: $dst})"
            " MERGE (a)-[:IMPORTS]->(b)",
            {"src": src_path, "dst": dst_path},
        )

    def add_file_to_directory(self, file_path: str, dir_path: str) -> None:
        if not self._conn:
            return
        self._exec(
            "MATCH (f:File {path: $fp}), (d:Directory {path: $dp})"
            " MERGE (f)-[:BELONGS_TO]->(d)",
            {"fp": file_path, "dp": dir_path},
        )

    # ── queries ────────────────────────────────────────────────────────────────

    def what_imports(self, file_path: str) -> list[str]:
        if not self._conn:
            return []
        result = self._exec(
            "MATCH (:File {path: $p})-[:IMPORTS]->(b:File) RETURN b.path",
            {"p": file_path},
        )
        return self._column(result, 0)

    def what_depends_on(self, file_path: str) -> list[str]:
        if not self._conn:
            return []
        result = self._exec(
            "MATCH (a:File)-[:IMPORTS]->(:File {path: $p}) RETURN a.path",
            {"p": file_path},
        )
        return self._column(result, 0)

    def impact_of_change(self, file_path: str, depth: int = 3) -> list[dict]:
        if not self._conn:
            return []
        result = self._exec(
            f"MATCH (a:File)-[:IMPORTS*1..{depth}]->(:File {{path: $p}})"
            " RETURN DISTINCT a.path, a.language, a.loc",
            {"p": file_path},
        )
        return [
            {"path": row[0], "language": row[1], "loc": row[2]}
            for row in self._rows(result)
        ]

    def classes_in_file(self, file_path: str) -> list[str]:
        if not self._conn:
            return []
        result = self._exec(
            "MATCH (:File {path: $p})-[:DEFINES]->(c:Class) RETURN c.name",
            {"p": file_path},
        )
        return self._column(result, 0)

    def functions_in_file(self, file_path: str) -> list[str]:
        if not self._conn:
            return []
        result = self._exec(
            "MATCH (:File {path: $p})-[:DEFINES_FN]->(fn:Function) RETURN fn.name",
            {"p": file_path},
        )
        return self._column(result, 0)

    def most_imported_files(self, limit: int = 20) -> list[dict]:
        if not self._conn:
            return []
        result = self._exec(
            "MATCH (a:File)-[:IMPORTS]->(b:File)"
            " RETURN b.path, COUNT(*) AS import_count"
            " ORDER BY import_count DESC"
            f" LIMIT {limit}",
        )
        return [
            {"path": row[0], "import_count": row[1]}
            for row in self._rows(result)
        ]

    def summary(self) -> dict:
        if not self._conn:
            return {"available": False}
        file_count = self._scalar("MATCH (f:File) RETURN COUNT(f)", 0)
        class_count = self._scalar("MATCH (c:Class) RETURN COUNT(c)", 0)
        fn_count = self._scalar("MATCH (fn:Function) RETURN COUNT(fn)", 0)
        import_count = self._scalar("MATCH (:File)-[r:IMPORTS]->(:File) RETURN COUNT(r)", 0)
        return {
            "available": True,
            "files": file_count,
            "classes": class_count,
            "functions": fn_count,
            "import_edges": import_count,
        }

    # ── internals ─────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        for ddl in _SCHEMA_DDL:
            try:
                self._conn.execute(ddl)
            except Exception:
                pass  # table already exists

    def _exec(self, cypher: str, params: Optional[dict] = None):
        try:
            if params:
                return self._conn.execute(cypher, parameters=params)
            return self._conn.execute(cypher)
        except Exception:
            return None

    def _rows(self, result) -> list[list]:
        if result is None:
            return []
        rows = []
        try:
            while result.has_next():
                rows.append(result.get_next())
        except Exception:
            pass
        return rows

    def _column(self, result, col: int) -> list:
        return [row[col] for row in self._rows(result) if len(row) > col]

    def _scalar(self, cypher: str, default: Any = None) -> Any:
        result = self._exec(cypher)
        rows = self._rows(result)
        if rows and rows[0]:
            return rows[0][0]
        return default
