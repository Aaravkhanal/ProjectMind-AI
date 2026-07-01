"""
Graph Serializer.

Converts a NetworkX DiGraph to/from JSON for API responses
and VS Code extension visualization.

Output format is D3.js compatible:
  { nodes: [{id, kind, ...attrs}], edges: [{source, target, kind}] }
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


class GraphSerializer:
    def to_dict(self, graph: nx.DiGraph) -> dict:
        nodes = []
        for node_id, data in graph.nodes(data=True):
            nodes.append({"id": node_id, **data})

        edges = []
        for src, dst, data in graph.edges(data=True):
            edges.append({"source": src, "target": dst, **data})

        return {"nodes": nodes, "edges": edges}

    def save(self, graph: nx.DiGraph, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(graph), indent=2))
        return path

    def load(self, path: Path) -> nx.DiGraph:
        data = json.loads(path.read_text())
        g = nx.DiGraph()
        for node in data["nodes"]:
            node_id = node.pop("id")
            g.add_node(node_id, **node)
        for edge in data["edges"]:
            src = edge.pop("source")
            dst = edge.pop("target")
            g.add_edge(src, dst, **edge)
        return g

    def to_file_only(self, graph: nx.DiGraph) -> dict:
        """Filtered view with only file-level nodes — lighter for visualization."""
        file_nodes = {n for n, d in graph.nodes(data=True) if d.get("kind") == "file"}
        sub = graph.subgraph(file_nodes)
        return self.to_dict(sub)
