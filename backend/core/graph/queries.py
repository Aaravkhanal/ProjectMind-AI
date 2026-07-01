"""
Knowledge Graph Queries.

Answers project-wide questions:
  - What breaks if I change file X?
  - What does file X depend on?
  - Which files are most critical?
  - What's the shortest dependency path from A to B?
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import networkx as nx


class GraphQueries:
    def __init__(self, graph: nx.DiGraph, project_root: str):
        self.graph = graph
        self.root = Path(project_root).resolve()

    # ------------------------------------------------------------------
    # Impact analysis — "what breaks if I change this?"
    # ------------------------------------------------------------------

    def impact_of(self, file_path: str) -> dict:
        """
        Returns all files that transitively depend on file_path.
        These files would need to be re-tested / re-reviewed if file_path changes.
        """
        rel = self._normalize(file_path)
        if rel not in self.graph:
            return {"file": rel, "affected_files": [], "depth": 0, "error": "file not in graph"}

        rev = self.graph.reverse(copy=False)
        descendants = [
            n for n in nx.descendants(rev, rel)
            if self._is_file(n)
        ]

        max_depth = 0
        for n in descendants:
            try:
                d = nx.shortest_path_length(rev, rel, n)
                max_depth = max(max_depth, d)
            except nx.NetworkXNoPath:
                pass

        return {
            "file": rel,
            "affected_files": sorted(descendants),
            "count": len(descendants),
            "depth": max_depth,
        }

    # ------------------------------------------------------------------
    # Dependency queries
    # ------------------------------------------------------------------

    def dependencies_of(self, file_path: str) -> dict:
        """Direct and transitive imports/references for a file."""
        rel = self._normalize(file_path)
        if rel not in self.graph:
            return {"file": rel, "direct": [], "transitive": [], "error": "file not in graph"}

        direct = [
            n for n in self.graph.successors(rel)
            if self._is_file(n)
        ]
        all_deps = [
            n for n in nx.descendants(self.graph, rel)
            if self._is_file(n)
        ]
        transitive = [n for n in all_deps if n not in direct]

        return {
            "file": rel,
            "direct": sorted(direct),
            "transitive": sorted(transitive),
        }

    def dependents_of(self, file_path: str, depth: int = 5) -> list[str]:
        """Files that directly or transitively import/reference this file."""
        rel = self._normalize(file_path)
        if rel not in self.graph:
            return []
        rev = self.graph.reverse(copy=False)
        reachable = nx.ego_graph(rev, rel, radius=depth, undirected=False)
        return sorted(n for n in reachable.nodes() if n != rel and self._is_file(n))

    # ------------------------------------------------------------------
    # Centrality — "which files are most critical?"
    # ------------------------------------------------------------------

    def most_central(self, top_n: int = 10) -> list[dict]:
        """
        Files ranked by PageRank on the file-only subgraph.
        High score = many other files depend on this one.
        """
        file_nodes = [n for n in self.graph.nodes() if self._is_file(n)]
        if len(file_nodes) < 2:
            return [{"file": f, "centrality_score": 1.0} for f in file_nodes]

        sub = self.graph.subgraph(file_nodes)
        try:
            scores = nx.pagerank(sub, max_iter=200)
        except nx.PowerIterationFailedConvergence:
            scores = {n: 1.0 / len(file_nodes) for n in file_nodes}

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [{"file": f, "centrality_score": round(s, 5)} for f, s in ranked]

    # ------------------------------------------------------------------
    # Path queries
    # ------------------------------------------------------------------

    def shortest_path(self, src: str, dst: str) -> Optional[list[str]]:
        """Shortest dependency path between two files."""
        src = self._normalize(src)
        dst = self._normalize(dst)
        try:
            return nx.shortest_path(self.graph, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def all_paths(self, src: str, dst: str, cutoff: int = 6) -> list[list[str]]:
        """All simple paths between src and dst (up to cutoff length)."""
        src = self._normalize(src)
        dst = self._normalize(dst)
        try:
            return list(nx.all_simple_paths(self.graph, src, dst, cutoff=cutoff))
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return []

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        file_nodes = [n for n in self.graph.nodes() if self._is_file(n)]
        fn_nodes = [n for n in self.graph.nodes() if self._node_kind(n) == "function"]
        class_nodes = [n for n in self.graph.nodes() if self._node_kind(n) == "class"]

        edge_kinds: dict[str, int] = {}
        for _, _, d in self.graph.edges(data=True):
            k = d.get("kind", "unknown")
            edge_kinds[k] = edge_kinds.get(k, 0) + 1

        return {
            "nodes": {
                "total": self.graph.number_of_nodes(),
                "files": len(file_nodes),
                "functions": len(fn_nodes),
                "classes": len(class_nodes),
            },
            "edges": {
                "total": self.graph.number_of_edges(),
                **edge_kinds,
            },
            "components": nx.number_weakly_connected_components(self.graph),
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            try:
                return str(p.relative_to(self.root))
            except ValueError:
                return path
        return path

    def _is_file(self, node_id: str) -> bool:
        return self.graph.nodes.get(node_id, {}).get("kind") == "file"

    def _node_kind(self, node_id: str) -> str:
        return self.graph.nodes.get(node_id, {}).get("kind", "unknown")
