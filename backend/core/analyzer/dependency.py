"""
Dependency Analyzer — builds an import graph and detects circular dependencies.
Also flags unused imports by comparing what was imported vs what was referenced.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from backend.core.analyzer.ast_parser import FileAnalysis, ImportInfo


@dataclass
class CircularDependency:
    cycle: list[str]

    def __str__(self) -> str:
        return " → ".join(self.cycle)


@dataclass
class UnusedImport:
    file: str
    line: int
    module: str
    name: str


@dataclass
class DependencyReport:
    import_graph: dict[str, list[str]]   # module → list of imported modules
    circular_dependencies: list[CircularDependency]
    unused_imports: list[UnusedImport]
    most_imported: list[tuple[str, int]]  # (module, import_count)


class DependencyAnalyzer:
    def __init__(self, project_root: str, file_analyses: list[FileAnalysis]):
        self.root = Path(project_root)
        self.analyses = file_analyses

    def analyze(self) -> DependencyReport:
        module_map = self._build_module_map()
        graph = self._build_import_graph(module_map)
        cycles = self._find_cycles(graph)
        unused = self._find_unused_imports()
        most_imported = self._most_imported_modules()

        return DependencyReport(
            import_graph=graph,
            circular_dependencies=cycles,
            unused_imports=unused,
            most_imported=most_imported,
        )

    # ------------------------------------------------------------------
    # Module map: file path → logical module name
    # ------------------------------------------------------------------

    def _build_module_map(self) -> dict[str, str]:
        """Map each source file to its dotted module name relative to the project root."""
        mapping: dict[str, str] = {}
        for analysis in self.analyses:
            filepath = Path(analysis.path)
            try:
                rel = filepath.relative_to(self.root)
            except ValueError:
                continue
            parts = list(rel.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            mapping[analysis.path] = ".".join(parts)
        return mapping

    # ------------------------------------------------------------------
    # Import graph: module → [imported modules that exist in this project]
    # ------------------------------------------------------------------

    def _build_import_graph(self, module_map: dict[str, str]) -> dict[str, list[str]]:
        known_modules = set(module_map.values())
        graph: dict[str, list[str]] = {m: [] for m in known_modules}

        for analysis in self.analyses:
            src_module = module_map.get(analysis.path)
            if src_module is None:
                continue

            for imp in analysis.imports:
                # Resolve relative imports to absolute
                target = self._resolve(imp, src_module)
                if target is None:
                    continue

                # Only track intra-project edges
                matched = self._match_module(target, known_modules)
                if matched and matched != src_module:
                    if matched not in graph[src_module]:
                        graph[src_module].append(matched)

        return graph

    def _resolve(self, imp: ImportInfo, src_module: str) -> str | None:
        if not imp.module:
            return None
        if not imp.module.startswith("."):
            return imp.module

        # Relative import: count leading dots
        dots = len(imp.module) - len(imp.module.lstrip("."))
        suffix = imp.module.lstrip(".")
        parts = src_module.split(".")
        base = parts[: max(0, len(parts) - dots)]
        if suffix:
            base.append(suffix)
        return ".".join(base)

    def _match_module(self, target: str, known: set[str]) -> str | None:
        """Return the known module that best matches target."""
        if target in known:
            return target
        # Check if target is a sub-path of a known module
        for m in known:
            if target.startswith(m + ".") or m.startswith(target + "."):
                return m
        return None

    # ------------------------------------------------------------------
    # Cycle detection (DFS, Tarjan-style coloring)
    # ------------------------------------------------------------------

    def _find_cycles(self, graph: dict[str, list[str]]) -> list[CircularDependency]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in graph}
        stack: list[str] = []
        cycles: list[CircularDependency] = []
        seen_cycles: set[frozenset] = set()

        def dfs(node: str):
            color[node] = GRAY
            stack.append(node)
            for neighbor in graph.get(node, []):
                if color.get(neighbor, BLACK) == WHITE:
                    dfs(neighbor)
                elif color.get(neighbor) == GRAY:
                    # Found a cycle — extract it from the stack
                    idx = stack.index(neighbor)
                    cycle = stack[idx:] + [neighbor]
                    key = frozenset(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(CircularDependency(cycle=cycle))
            stack.pop()
            color[node] = BLACK

        for node in list(graph.keys()):
            if color[node] == WHITE:
                dfs(node)

        return cycles

    # ------------------------------------------------------------------
    # Unused imports
    # ------------------------------------------------------------------

    def _find_unused_imports(self) -> list[UnusedImport]:
        unused: list[UnusedImport] = []
        for analysis in self.analyses:
            used = analysis.used_names
            for imp in analysis.imports:
                # Skip __future__ and TYPE_CHECKING-gated imports
                if imp.module in ("__future__", "typing") or "TYPE_CHECKING" in imp.module:
                    continue
                # Skip wildcard imports
                if imp.names == ["*"]:
                    continue

                if imp.is_from:
                    for name in imp.names:
                        if name not in used and name != "*":
                            unused.append(UnusedImport(
                                file=analysis.path,
                                line=imp.line,
                                module=imp.module,
                                name=name,
                            ))
                else:
                    # `import module [as alias]`
                    ref_name = imp.alias or imp.module.split(".")[0]
                    if ref_name not in used:
                        unused.append(UnusedImport(
                            file=analysis.path,
                            line=imp.line,
                            module=imp.module,
                            name=ref_name,
                        ))
        return unused

    # ------------------------------------------------------------------
    # Most imported modules
    # ------------------------------------------------------------------

    def _most_imported_modules(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = defaultdict(int)
        for analysis in self.analyses:
            for imp in analysis.imports:
                counts[imp.module] += 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]
