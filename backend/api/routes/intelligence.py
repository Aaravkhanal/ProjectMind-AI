"""
Phase 21–23 Intelligence API.

/intelligence/architecture/*     — Architecture Memory (Phase 21)
/intelligence/decisions/*        — Decision Store (Phase 21)
/intelligence/agents/*           — Agent Memory (Phase 21)
/intelligence/graph/*            — Knowledge Graph (Phase 22)
/intelligence/vectors/*          — Vector Memory (Phase 23)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _brain(project_path: str):
    from backend.core.intelligence.brain import IntelligenceBrain
    return IntelligenceBrain(project_path)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 21 — Architecture Memory
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/architecture", summary="Load or scan architecture memory")
def get_architecture(
    project_path: str = ".",
    rescan: bool = Query(False, description="Force a fresh repo scan"),
):
    b = _brain(project_path)
    if rescan:
        return b.architecture.scan(project_path)
    data = b.architecture.load()
    if not data.get("languages"):
        data = b.architecture.scan(project_path)
    return data


@router.post("/architecture/scan", summary="Force re-scan of architecture")
def scan_architecture(project_path: str = "."):
    b = _brain(project_path)
    return b.architecture.scan(project_path)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 21 — Decision Store
# ══════════════════════════════════════════════════════════════════════════════

class DecisionRequest(BaseModel):
    project_path: str
    decision: str
    reasoning: str
    alternatives: list[str] = []
    models_used: list[str] = []
    confidence: float = 0.8
    category: str = "architecture"


@router.post("/decisions", summary="Record an architectural decision")
def record_decision(req: DecisionRequest):
    b = _brain(req.project_path)
    d = b.decisions.record(
        project_path=req.project_path,
        decision=req.decision,
        reasoning=req.reasoning,
        alternatives=req.alternatives,
        models_used=req.models_used,
        confidence=req.confidence,
        category=req.category,
    )
    return b.decisions.serialize(d)


@router.get("/decisions", summary="List architectural decisions")
def list_decisions(
    project_path: str = ".",
    category: Optional[str] = None,
    limit: int = 50,
):
    b = _brain(project_path)
    decisions = b.decisions.list(project_path, category=category, limit=limit)
    return [b.decisions.serialize(d) for d in decisions]


@router.get("/decisions/{decision_id}", summary="Get a specific decision")
def get_decision(decision_id: str, project_path: str = "."):
    b = _brain(project_path)
    d = b.decisions.get(decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision not found")
    return b.decisions.serialize(d)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 21 — Agent Memory
# ══════════════════════════════════════════════════════════════════════════════

class AgentRunRequest(BaseModel):
    project_path: str
    agent_name: str
    task_type: str = "review"
    success: bool = True
    confidence: float = 0.0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    tokens_used: int = 0
    model_used: str = ""
    prompt_text: Optional[str] = None


@router.post("/agents/record", summary="Record an agent run")
def record_agent_run(req: AgentRunRequest):
    b = _brain(req.project_path)
    record = b.agents.record_run(
        project_path=req.project_path,
        agent_name=req.agent_name,
        task_type=req.task_type,
        success=req.success,
        confidence=req.confidence,
        cost_usd=req.cost_usd,
        latency_ms=req.latency_ms,
        tokens_used=req.tokens_used,
        model_used=req.model_used,
        prompt_text=req.prompt_text,
    )
    return {"id": record.id, "agent_name": record.agent_name, "success": record.success}


@router.get("/agents", summary="Summary of all agents' performance")
def get_all_agents(project_path: str = "."):
    b = _brain(project_path)
    return b.agents.get_all_agents_summary(project_path)


@router.get("/agents/{agent_name}", summary="Stats for a specific agent")
def get_agent_stats(agent_name: str, project_path: str = "."):
    b = _brain(project_path)
    return b.agents.get_agent_stats(project_path, agent_name)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 22 — Knowledge Graph
# ══════════════════════════════════════════════════════════════════════════════

class AddFileRequest(BaseModel):
    project_path: str
    path: str
    language: str = ""
    loc: int = 0


class AddImportRequest(BaseModel):
    project_path: str
    src_path: str
    dst_path: str


class IndexRepoRequest(BaseModel):
    project_path: str


@router.get("/graph/summary", summary="Knowledge graph statistics")
def graph_summary(project_path: str = "."):
    b = _brain(project_path)
    if not b.graph.available:
        return {"available": False, "reason": "kuzu not installed — pip install projectmind[intelligence]"}
    return b.graph.summary()


@router.post("/graph/file", summary="Add a file node to the graph")
def graph_add_file(req: AddFileRequest):
    b = _brain(req.project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    b.graph.add_file(req.path, req.language, req.loc)
    return {"ok": True}


@router.post("/graph/import", summary="Record an import relationship")
def graph_add_import(req: AddImportRequest):
    b = _brain(req.project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    b.graph.add_import(req.src_path, req.dst_path)
    return {"ok": True}


@router.get("/graph/impact/{file_path:path}", summary="Impact analysis: files affected if this file changes")
def graph_impact(file_path: str, project_path: str = ".", depth: int = 3):
    b = _brain(project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    return {"file": file_path, "affected": b.graph.impact_of_change(file_path, depth)}


@router.get("/graph/dependents/{file_path:path}", summary="Files that import this file")
def graph_dependents(file_path: str, project_path: str = "."):
    b = _brain(project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    return {"file": file_path, "dependents": b.graph.what_depends_on(file_path)}


@router.get("/graph/imports/{file_path:path}", summary="Files imported by this file")
def graph_imports(file_path: str, project_path: str = "."):
    b = _brain(project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    return {"file": file_path, "imports": b.graph.what_imports(file_path)}


@router.get("/graph/hotspots", summary="Most-imported files in the graph")
def graph_hotspots(project_path: str = ".", limit: int = 20):
    b = _brain(project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")
    return b.graph.most_imported_files(limit)


@router.post("/graph/index", summary="Index full repository into the knowledge graph")
def graph_index_repo(req: IndexRepoRequest):
    b = _brain(req.project_path)
    if not b.graph.available:
        raise HTTPException(status_code=503, detail="kuzu not installed")

    from backend.core.analyzer.ast_parser import ASTParser
    from backend.core.graph.builder import GraphBuilder
    import pathlib

    root = pathlib.Path(req.project_path).resolve()
    skip = {".venv", "node_modules", ".git", "__pycache__", "dist", ".next"}
    py_files = [
        str(f) for f in root.rglob("*.py")
        if not any(p in f.parts for p in skip)
    ]

    parser = ASTParser()
    analyses = [parser.parse(f) for f in py_files[:200]]  # cap at 200

    indexed_files = 0
    indexed_imports = 0
    for a in analyses:
        if a.parse_error:
            continue
        try:
            rel = str(pathlib.Path(a.path).relative_to(root))
        except ValueError:
            rel = a.path
        lang = "Python"
        b.graph.add_file(rel, lang, a.loc)
        for cls in a.classes:
            b.graph.add_class(rel, cls.name, len(cls.methods), cls.line_start)
        for fn in a.functions:
            b.graph.add_function(
                rel, fn.name, fn.qualified_name,
                fn.complexity, fn.is_async, fn.line_start,
                fn.parent_class,
            )
        indexed_files += 1

    # Import edges require the module map — use GraphBuilder to resolve them
    builder = GraphBuilder(req.project_path)
    nx_graph = builder.build(analyses)
    for src, dst, data in nx_graph.edges(data=True):
        if data.get("kind") == "imports":
            b.graph.add_import(src, dst)
            indexed_imports += 1

    return {
        "indexed_files": indexed_files,
        "indexed_imports": indexed_imports,
        "graph_summary": b.graph.summary(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Phase 23 — Vector Memory
# ══════════════════════════════════════════════════════════════════════════════

class EmbedRequest(BaseModel):
    project_path: str
    content: str
    type: str
    path: str = ""
    importance: float = 0.5
    agent: str = ""
    metadata: dict = {}
    api_key: Optional[str] = None
    embedding_model: str = "text-embedding-ada-002"


class VectorSearchRequest(BaseModel):
    project_path: str
    query: str
    type_filter: Optional[str] = None
    k: int = 10
    api_key: Optional[str] = None
    embedding_model: str = "text-embedding-ada-002"


@router.get("/vectors/summary", summary="Vector memory statistics")
def vectors_summary(project_path: str = "."):
    b = _brain(project_path)
    if not b.vectors.available:
        return {"available": False, "reason": "lancedb not installed — pip install projectmind[intelligence]"}
    return b.vectors.summary()


@router.post("/vectors/embed", summary="Embed and store a piece of content")
def embed_content(req: EmbedRequest):
    b = _brain(req.project_path)
    if not b.vectors.available:
        raise HTTPException(status_code=503, detail="lancedb not installed")
    doc_id = b.vectors.embed(
        content=req.content,
        type=req.type,
        project=req.project_path,
        path=req.path,
        importance=req.importance,
        agent=req.agent,
        metadata=req.metadata,
        api_key=req.api_key,
        embedding_model=req.embedding_model,
    )
    if doc_id is None:
        raise HTTPException(status_code=422, detail="Embedding failed — check API key and model")
    return {"id": doc_id}


@router.post("/vectors/search", summary="Semantic search across vector memory")
def vector_search(req: VectorSearchRequest):
    b = _brain(req.project_path)
    if not b.vectors.available:
        raise HTTPException(status_code=503, detail="lancedb not installed")
    results = b.vectors.search(
        query=req.query,
        type_filter=req.type_filter,
        project=req.project_path,
        k=req.k,
        api_key=req.api_key,
        embedding_model=req.embedding_model,
    )
    return {"query": req.query, "results": results}


@router.post("/vectors/search/bugs", summary="Find bugs similar to a description")
def search_bugs(req: VectorSearchRequest):
    b = _brain(req.project_path)
    if not b.vectors.available:
        raise HTTPException(status_code=503, detail="lancedb not installed")
    return {"results": b.vectors.search_similar_bugs(req.query, req.project_path, req.k, req.api_key)}


@router.post("/vectors/search/decisions", summary="Find related architectural decisions")
def search_decisions(req: VectorSearchRequest):
    b = _brain(req.project_path)
    if not b.vectors.available:
        raise HTTPException(status_code=503, detail="lancedb not installed")
    return {"results": b.vectors.search_similar_decisions(req.query, req.project_path, req.k, req.api_key)}
