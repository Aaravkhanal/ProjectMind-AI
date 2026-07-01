"""
ProjectMind AI — MCP Server

Exposes ProjectMind's core capabilities as MCP tools so Claude Code,
Cursor, Windsurf, and any MCP-compatible agent can call them natively.

Tools:
  get_project_context   — compressed context + memories for a task (core value prop)
  search_memory         — semantic search across past decisions / errors / patterns
  add_decision          — record an architectural decision
  add_error             — record a bug and its fix
  get_impact            — blast radius of changing a file
  get_health            — project health score
  analyze_project       — run DNA extraction + init .projectmind/
  list_patterns         — show established coding patterns
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load env vars so LLM keys are available when tools run
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(_repo_root / ".env.local", override=True)
load_dotenv(_repo_root / ".env")

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("projectmind.mcp")

mcp = FastMCP(
    "ProjectMind AI",
    instructions=(
        "ProjectMind is the persistent memory layer for AI coding agents. "
        "Always call get_project_context at the start of any coding task. "
        "Call search_memory before implementing anything to check for past decisions. "
        "Call add_decision or add_error after completing a task to persist what you learned."
    ),
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_pm(project_path: str) -> Path:
    root = Path(project_path).resolve()
    pm = root / ".projectmind"
    if not pm.exists():
        raise FileNotFoundError(
            f"No .projectmind/ directory found at {root}.\n"
            f"Fix: run  projectmind init {root}"
        )
    return root


def _require_db(root: Path) -> Path:
    db = root / ".projectmind" / "memory.db"
    if not db.exists():
        raise FileNotFoundError(
            f"No memory.db at {db}.\n"
            f"Fix: run  projectmind init {root}"
        )
    return db


# ---------------------------------------------------------------------------
# Tool 1 — get_project_context  (the core value prop)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Get a token-efficient context summary for any coding task. "
        "Returns the project's language, frameworks, architecture, coding conventions, "
        "relevant past decisions, known bugs to avoid, and established patterns — "
        "all compressed to ~500 tokens. "
        "ALWAYS call this at the start of a coding task before writing any code."
    )
)
def get_project_context(project_path: str, task: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
        task: What you want to implement or fix (e.g. 'add JWT auth middleware').
    """
    root = _require_pm(project_path)
    pm_dir = root / ".projectmind"

    # Session continuity — inject previous session context
    session_block = ""
    try:
        from backend.core.session.tracker import SessionTracker
        tracker = SessionTracker(pm_dir)
        tracker.start_or_resume(task)
        session_block = tracker.build_context_block()
    except Exception:
        pass

    from backend.core.prompt.generator import SmartPromptGenerator
    gen = SmartPromptGenerator(str(root))
    result = gen.generate(task=task)
    tokens = result["token_estimate"]
    memories = result["relevant_memories"]

    # Record token savings
    try:
        from backend.core.token_stats import TokenStats, estimate_raw_tokens
        stats = TokenStats(pm_dir)
        raw = estimate_raw_tokens(root)
        saved = stats.record(tokens_used=tokens, raw_codebase_tokens=raw, tool="mcp-context")
        savings_note = f" · saved ~{saved:,} tokens"
    except Exception:
        savings_note = ""

    tag = (
        f"[ProjectMind · {tokens} tokens · {len(memories)} memories matched{savings_note}]"
        if memories else
        f"[ProjectMind · {tokens} tokens{savings_note}]"
    )
    prompt = result["prompt"]
    if session_block:
        prompt = f"{session_block}\n\n---\n\n{prompt}"
    return f"{prompt}\n\n{tag}"


# ---------------------------------------------------------------------------
# Tool 2 — search_memory
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search the project's persistent memory for past decisions, known errors, "
        "patterns, or tasks. "
        "Call this before implementing anything to check if the team has solved it before."
    )
)
def search_memory(
    project_path: str,
    query: str,
    types: str = "",
    k: int = 5,
) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
        query: Natural language search query.
        types: Optional comma-separated filter — any of: decisions, errors, patterns, tasks.
        k: Maximum number of results to return (default 5).
    """
    root = _require_pm(project_path)
    db = _require_db(root)

    from backend.core.memory.store import MemoryStore
    store = MemoryStore(str(db), enable_vectors=True)
    store.init_db()

    memory_types = [t.strip() for t in types.split(",") if t.strip()] or None
    results = store.search(query, k=k, memory_types=memory_types)

    if not results:
        return f"No memories found matching: {query!r}"

    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, r in enumerate(results, 1):
        score_str = f"  score={r['score']:.3f}" if r.get("score") else ""
        lines.append(f"{i}. [{r['type'].upper()}]{score_str}")
        lines.append(f"   {r['content'][:400]}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — add_decision
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Record an architectural or technical decision in the project memory. "
        "Future agents will see this and won't re-litigate settled choices. "
        "Call this after making any significant technical decision."
    )
)
def add_decision(project_path: str, decision: str, reason: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
        decision: What was decided (e.g. 'Use JWT for authentication').
        reason: Why this decision was made (e.g. 'Stateless, works across microservices').
    """
    root = _require_pm(project_path)
    db = _require_db(root)

    from backend.core.memory.store import MemoryStore
    store = MemoryStore(str(db), enable_vectors=True)
    store.init_db()
    record = store.add_decision(str(root), decision, reason)
    return f"Decision #{record.id} saved.\n\nDecision: {decision}\nReason: {reason}"


# ---------------------------------------------------------------------------
# Tool 4 — add_error
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Record a bug and its fix in the project memory. "
        "Future agents will be warned before making the same mistake. "
        "Call this after resolving any non-obvious bug or gotcha."
    )
)
def add_error(
    project_path: str,
    error: str,
    fix: str,
    confidence: float = 0.8,
) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
        error: Description of the error or bug encountered.
        fix: How it was resolved.
        confidence: How confident you are in the fix (0.0–1.0, default 0.8).
    """
    root = _require_pm(project_path)
    db = _require_db(root)

    from backend.core.memory.store import MemoryStore
    store = MemoryStore(str(db), enable_vectors=True)
    store.init_db()
    record = store.add_error(str(root), error, fix, confidence)
    return (
        f"Error #{record.id} saved (confidence: {record.confidence:.0%}).\n\n"
        f"Error: {error}\nFix: {fix}"
    )


# ---------------------------------------------------------------------------
# Tool 5 — get_impact
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Find all files that would be affected if the given file changes. "
        "Use this before refactoring a file to understand the blast radius. "
        "Requires the knowledge graph to be built first (projectmind graph build)."
    )
)
def get_impact(project_path: str, file: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
        file: Relative path to the file you want to change (e.g. 'backend/core/memory/store.py').
    """
    root = _require_pm(project_path)
    graph_file = root / ".projectmind" / "knowledge_graph" / "graph.json"

    if not graph_file.exists():
        return (
            "Knowledge graph has not been built yet.\n"
            f"Fix: run  projectmind graph build {root}"
        )

    from backend.core.graph.queries import GraphQueries
    from backend.core.graph.serializer import GraphSerializer

    g = GraphSerializer().load(graph_file)
    q = GraphQueries(g, str(root))
    result = q.impact_of(file)
    affected = result["affected_files"]

    if not affected:
        return f"No other files depend on {file} — safe to change in isolation."

    lines = [
        f"Changing  {file}  affects {len(affected)} file(s)  "
        f"(dependency depth: {result['depth']}):\n"
    ]
    for f_path in sorted(affected):
        lines.append(f"  → {f_path}")
    lines.append(
        f"\nRecommendation: review and re-test the {len(affected)} file(s) above "
        "after making changes."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6 — get_health
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Get the current health score for the project — architecture, security, "
        "maintainability, and a breakdown of issues. "
        "Requires static analysis to have run (projectmind analyze)."
    )
)
def get_health(project_path: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
    """
    root = _require_pm(project_path)
    health_file = root / ".projectmind" / "health_score.json"

    if not health_file.exists():
        return (
            "Health score not available yet.\n"
            f"Fix: run  projectmind analyze {root}"
        )

    data = json.loads(health_file.read_text())
    b = data.get("breakdown", {})

    def _grade(score: float) -> str:
        if score >= 8.5: return "excellent"
        if score >= 7.0: return "good"
        if score >= 5.0: return "fair"
        return "needs work"

    lines = [
        f"Project Health: {data['overall']}/10  ({_grade(data['overall'])})\n",
        f"  Architecture     {data['architecture']}/10  ({_grade(data['architecture'])})",
        f"  Security         {data['security']}/10  ({_grade(data['security'])})",
        f"  Maintainability  {data['maintainability']}/10  ({_grade(data['maintainability'])})",
        f"  Code Quality     {data['code_quality']}/10  ({_grade(data['code_quality'])})",
        "",
        "Issue breakdown:",
        f"  Circular dependencies  {b.get('circular_dependencies', 0)}",
        f"  Duplicate functions    {b.get('duplicate_functions', 0)}",
        f"  Dead functions         {b.get('dead_functions', 0)}",
        f"  Dead classes           {b.get('dead_classes', 0)}",
        f"  Security errors        {b.get('security_errors', 0)}",
        f"  Security warnings      {b.get('security_warnings', 0)}",
        f"  High complexity funcs  {b.get('high_complexity_functions', 0)}",
        f"  Parse errors           {b.get('parse_errors', 0)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7 — analyze_project
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Initialize or refresh the .projectmind/ memory directory for a project. "
        "Extracts project DNA (language, frameworks, architecture, patterns) and "
        "writes context files. Run once when starting work on a new project."
    )
)
def analyze_project(project_path: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root to analyze.
    """
    root = Path(project_path).resolve()
    if not root.exists():
        return f"Path does not exist: {root}"

    from backend.core.dna.extractor import DNAExtractor
    from backend.core.dna.generator import DNAGenerator

    dna = DNAExtractor(str(root)).extract()
    pm_dir = DNAGenerator(dna).generate()
    files = [f.name for f in sorted(pm_dir.iterdir()) if f.is_file()]

    return (
        f"Project analyzed and .projectmind/ initialized at {pm_dir}\n\n"
        f"Detected:\n"
        f"  Language     : {dna.language}\n"
        f"  Frameworks   : {', '.join(dna.frameworks) or 'none'}\n"
        f"  Architecture : {dna.architecture_pattern}\n"
        f"  Database     : {dna.database or 'none'}\n"
        f"  Deployment   : {', '.join(dna.deployment) or 'none'}\n"
        f"  Source files : {dna.source_files} / {dna.total_files} total\n\n"
        f"Files written: {', '.join(files)}"
    )


# ---------------------------------------------------------------------------
# Tool 8 — list_patterns
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List the established coding patterns stored in project memory. "
        "Always follow these patterns when generating code for this project."
    )
)
def list_patterns(project_path: str) -> str:
    """
    Args:
        project_path: Absolute path to the project root.
    """
    root = _require_pm(project_path)
    db = _require_db(root)

    from backend.core.memory.store import MemoryStore
    store = MemoryStore(str(db))
    store.init_db()
    patterns = store.list_patterns(str(root))

    if not patterns:
        patterns_file = root / ".projectmind" / "patterns.md"
        if patterns_file.exists():
            return patterns_file.read_text()
        return "No patterns recorded yet."

    lines = [f"Established patterns for {root.name}:\n"]
    for p in patterns:
        lines.append(f"[{p.category.upper()}] {p.name}")
        lines.append(f"  {p.description}")
        if p.example:
            lines.append(f"  Example: {p.example[:200]}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
