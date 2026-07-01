from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.analyzer.ast_parser import ProjectParser
from backend.core.graph.builder import GraphBuilder
from backend.core.graph.queries import GraphQueries
from backend.core.graph.serializer import GraphSerializer

router = APIRouter(prefix="/graph", tags=["graph"])

_GRAPH_FILE = ".projectmind/knowledge_graph/graph.json"
_serializer = GraphSerializer()


def _load_graph(project_path: str):
    graph_path = Path(project_path) / _GRAPH_FILE
    if not graph_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Graph not built yet. Run POST /graph/build first.",
        )
    return _serializer.load(graph_path)


# ------------------------------------------------------------------
# Build
# ------------------------------------------------------------------

class BuildRequest(BaseModel):
    project_path: str
    max_files: int = 500
    save: bool = True


@router.post("/build")
def build_graph(req: BuildRequest):
    root = Path(req.project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")

    analyses = ProjectParser(str(root)).parse(max_files=req.max_files)
    graph = GraphBuilder(str(root)).build(analyses)

    graph_path = None
    if req.save:
        out = root / _GRAPH_FILE
        _serializer.save(graph, out)
        graph_path = str(out)

    q = GraphQueries(graph, str(root))
    return {
        "project_path": str(root),
        "summary": q.summary(),
        "graph_path": graph_path,
    }


# ------------------------------------------------------------------
# Serve graph JSON
# ------------------------------------------------------------------

@router.get("")
def get_graph(project_path: str, files_only: bool = False):
    graph = _load_graph(project_path)
    if files_only:
        return _serializer.to_file_only(graph)
    return _serializer.to_dict(graph)


# ------------------------------------------------------------------
# Impact analysis
# ------------------------------------------------------------------

@router.get("/impact")
def get_impact(project_path: str, file: str):
    graph = _load_graph(project_path)
    q = GraphQueries(graph, project_path)
    return q.impact_of(file)


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

@router.get("/dependencies")
def get_dependencies(project_path: str, file: str):
    graph = _load_graph(project_path)
    q = GraphQueries(graph, project_path)
    return q.dependencies_of(file)


# ------------------------------------------------------------------
# Most central files
# ------------------------------------------------------------------

@router.get("/central")
def get_central(project_path: str, top: int = 10):
    graph = _load_graph(project_path)
    q = GraphQueries(graph, project_path)
    return q.most_central(top_n=top)


# ------------------------------------------------------------------
# Shortest path between two files
# ------------------------------------------------------------------

@router.get("/path")
def get_path(project_path: str, src: str, dst: str):
    graph = _load_graph(project_path)
    q = GraphQueries(graph, project_path)
    path = q.shortest_path(src, dst)
    if path is None:
        return {"src": src, "dst": dst, "path": None, "reachable": False}
    return {"src": src, "dst": dst, "path": path, "reachable": True, "hops": len(path) - 1}


# ------------------------------------------------------------------
# Summary stats
# ------------------------------------------------------------------

@router.get("/summary")
def get_summary(project_path: str):
    graph = _load_graph(project_path)
    q = GraphQueries(graph, project_path)
    return q.summary()
