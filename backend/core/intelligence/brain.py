"""
IntelligenceBrain — single entry point for all Phase 21–23 subsystems.

Resolves .brain/ directory per project and lazily initialises each layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.intelligence.architecture import ArchitectureMemory
from backend.core.intelligence.decisions import DecisionStore
from backend.core.intelligence.agent_memory import AgentMemoryStore
from backend.core.intelligence.knowledge_graph import KnowledgeGraph
from backend.core.intelligence.vector_memory import VectorMemory


def _brain_dir(project_path: str) -> Path:
    d = Path(project_path).resolve() / ".brain"
    d.mkdir(parents=True, exist_ok=True)
    return d


class IntelligenceBrain:
    def __init__(self, project_path: str):
        self._root = project_path
        self._dir = _brain_dir(project_path)

        self.architecture = ArchitectureMemory(self._dir)
        self.decisions = DecisionStore(self._dir)
        self.agents = AgentMemoryStore(self._dir)
        self.graph = KnowledgeGraph(self._dir)
        self.vectors = VectorMemory(self._dir)

    @property
    def brain_dir(self) -> Path:
        return self._dir
