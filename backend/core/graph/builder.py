"""
Knowledge Graph Builder.

Builds a directed graph from AST analysis results.

Node types:
  file      — a source file (id = relative path from project root)
  function  — a function or method  (id = "rel/path.py::ClassName.method")
  class     — a class               (id = "rel/path.py::ClassName")

Edge types:
  imports     — file A imports from file B
  defines     — file defines a function / class
  contains    — class contains a method-function node
  inherits    — class A inherits from class B
  references  — file A uses a name defined in file B (cross-file, not via import)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import networkx as nx

from backend.core.analyzer.ast_parser import FileAnalysis, ImportInfo


class GraphBuilder:
    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, analyses: list[FileAnalysis]) -> nx.DiGraph:
        g = nx.DiGraph()
        ok = [a for a in analyses if not a.parse_error]

        module_map = self._build_module_map(ok)

        self._add_file_nodes(g, ok)
        self._add_definition_nodes(g, ok)
        self._add_import_edges(g, ok, module_map)
        self._add_inheritance_edges(g, ok)
        self._add_reference_edges(g, ok)

        return g

    # ------------------------------------------------------------------
    # Node construction
    # ------------------------------------------------------------------

    def _add_file_nodes(self, g: nx.DiGraph, analyses: list[FileAnalysis]) -> None:
        for a in analyses:
            rel = self._rel(a.path)
            g.add_node(
                rel,
                kind="file",
                loc=a.loc,
                functions=len(a.functions),
                classes=len(a.classes),
            )

    def _add_definition_nodes(self, g: nx.DiGraph, analyses: list[FileAnalysis]) -> None:
        for a in analyses:
            rel = self._rel(a.path)

            for fn in a.functions:
                node_id = f"{rel}::{fn.qualified_name}"
                g.add_node(
                    node_id,
                    kind="function",
                    name=fn.name,
                    complexity=fn.complexity,
                    is_async=fn.is_async,
                    is_method=fn.is_method,
                    line=fn.line_start,
                )
                g.add_edge(rel, node_id, kind="defines")

                # class → method edge
                if fn.is_method and fn.parent_class:
                    class_id = f"{rel}::{fn.parent_class}"
                    if g.has_node(class_id):
                        g.add_edge(class_id, node_id, kind="contains")

            for cl in a.classes:
                node_id = f"{rel}::{cl.name}"
                g.add_node(
                    node_id,
                    kind="class",
                    name=cl.name,
                    method_count=len(cl.methods),
                    line=cl.line_start,
                )
                g.add_edge(rel, node_id, kind="defines")

    # ------------------------------------------------------------------
    # Import edges (file → file)
    # ------------------------------------------------------------------

    def _add_import_edges(
        self,
        g: nx.DiGraph,
        analyses: list[FileAnalysis],
        module_map: dict[str, str],
    ) -> None:
        for a in analyses:
            src = self._rel(a.path)
            for imp in a.imports:
                dst = self._resolve_import(imp, src, module_map)
                if dst and dst != src and g.has_node(dst) and not g.has_edge(src, dst):
                    g.add_edge(src, dst, kind="imports")

    def _resolve_import(
        self,
        imp: ImportInfo,
        current_rel: str,
        module_map: dict[str, str],
    ) -> Optional[str]:
        module = imp.module

        if module.startswith("."):
            # Relative import — resolve against current package
            dots = len(module) - len(module.lstrip("."))
            rest = module.lstrip(".")
            parts = current_rel.replace("\\", "/").split("/")
            base_parts = parts[:-dots] if dots <= len(parts) else []
            if rest:
                candidate = "/".join(base_parts) + "/" + rest.replace(".", "/") + ".py"
            else:
                candidate = "/".join(base_parts) + "/__init__.py"
            return candidate if candidate in module_map.values() else None

        # Direct module match
        if module in module_map:
            return module_map[module]

        # Sub-path match: "backend.core.memory" might match "backend/core/memory/__init__.py"
        as_path = module.replace(".", "/")
        for mod, rel in module_map.items():
            if mod.startswith(module) or rel.startswith(as_path):
                return rel

        return None

    # ------------------------------------------------------------------
    # Inheritance edges (class → class)
    # ------------------------------------------------------------------

    def _add_inheritance_edges(self, g: nx.DiGraph, analyses: list[FileAnalysis]) -> None:
        # name → node_id for all classes
        class_index: dict[str, str] = {}
        for a in analyses:
            rel = self._rel(a.path)
            for cl in a.classes:
                class_index[cl.name] = f"{rel}::{cl.name}"

        for a in analyses:
            rel = self._rel(a.path)
            for cl in a.classes:
                src_id = f"{rel}::{cl.name}"
                for base in cl.base_classes:
                    # base may be "BaseModel" or "module.BaseModel"
                    base_name = base.split(".")[-1]
                    dst_id = class_index.get(base_name)
                    if dst_id and dst_id != src_id and not g.has_edge(src_id, dst_id):
                        g.add_edge(src_id, dst_id, kind="inherits")

    # ------------------------------------------------------------------
    # Cross-file reference edges (file → file, name-based)
    # ------------------------------------------------------------------

    def _add_reference_edges(self, g: nx.DiGraph, analyses: list[FileAnalysis]) -> None:
        # name → rel for all publicly defined names
        name_to_file: dict[str, str] = {}
        for a in analyses:
            rel = self._rel(a.path)
            for name in a.defined_names:
                name_to_file[name] = rel

        for a in analyses:
            src = self._rel(a.path)
            for name in a.used_names:
                dst = name_to_file.get(name)
                if dst and dst != src and not g.has_edge(src, dst):
                    g.add_edge(src, dst, kind="references")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_module_map(self, analyses: list[FileAnalysis]) -> dict[str, str]:
        """Maps dotted module name → relative file path."""
        m: dict[str, str] = {}
        for a in analyses:
            rel = self._rel(a.path)
            module = rel.replace("\\", "/").replace("/", ".").removesuffix(".py")
            # Also strip trailing .__init__
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            m[module] = rel
        return m

    def _rel(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return path
