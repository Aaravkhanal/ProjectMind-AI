"""
ProjectMind CLI — projectmind <command> [options]
"""

import json
import os
import sys
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    click.echo(click.style("  ✓ ", fg="green") + msg)

def _info(msg: str) -> None:
    click.echo(click.style("  · ", fg="cyan") + msg)

def _warn(msg: str) -> None:
    click.echo(click.style("  ⚠ ", fg="yellow") + msg, err=True)

def _err(msg: str) -> None:
    click.echo(click.style("  ✗ ", fg="red") + msg, err=True)

def _header(title: str) -> None:
    click.echo()
    click.echo(click.style(f" {title}", fg="bright_white", bold=True))
    click.echo(click.style(" " + "─" * (len(title) + 1), fg="bright_black"))


@click.group()
@click.version_option("0.2.0", prog_name="projectmind")
def cli():
    """ProjectMind AI — the persistent memory layer for AI coding agents."""


# ---------------------------------------------------------------------------
# projectmind init
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--llm", is_flag=True, default=False, help="Enhance with LLM architectural summary")
@click.option("--api-key", envvar="API_KEY", help="LLM API key (or set API_KEY env var)")
@click.option("--model", default=None, help="LLM model name (default: gpt-4o-mini)")
@click.option("--provider", default="openai", type=click.Choice(["openai", "ollama", "anthropic", "nvidia"]))
def init(path: str, llm: bool, api_key: str | None, model: str | None, provider: str):
    """Analyze a project and initialize its .projectmind/ memory directory."""
    from backend.core.dna.extractor import DNAExtractor
    from backend.core.dna.generator import DNAGenerator

    root = Path(path).resolve()
    _header(f"Initializing  {root.name}")

    extractor = DNAExtractor(str(root))
    dna = extractor.extract()

    _info(f"Language      {click.style(dna.language, fg='cyan')}")
    _info(f"Frameworks    {', '.join(dna.frameworks) or 'none'}")
    _info(f"Architecture  {click.style(dna.architecture_pattern, fg='yellow')}")
    _info(f"Database      {dna.database or 'none'}")
    _info(f"Auth          {dna.auth_strategy or 'none'}")
    _info(f"Tests         {'yes (' + dna.test_framework + ')' if dna.has_tests and dna.test_framework else 'none detected'}")
    _info(f"Deployment    {', '.join(dna.deployment) or 'none'}")
    _info(f"Source files  {dna.source_files} / {dna.total_files} total")

    llm_summary = None
    if llm:
        click.echo("\n🤖 Generating LLM architectural summary …")
        try:
            from langchain_core.output_parsers import StrOutputParser
            from backend.llm.providers import LLM, LLMProvider, PromptTemplate

            lm = LLM(
                model_name=model or os.environ.get("CODE_MODEL", "gpt-4o-mini"),
                provider=LLMProvider(provider),
                api_key=api_key,
            )
            prompt = LLM.load_prompt(PromptTemplate.DNA_EXTRACT)
            assert lm.model is not None
            chain = prompt | lm.model | StrOutputParser()
            llm_summary = chain.invoke({
                "dna_data": json.dumps(dna.to_dict(), indent=2),
                "folder_structure": "\n".join(dna.folder_structure),
            })
        except Exception as e:
            click.echo(f"  ⚠️  LLM enhancement failed: {e}", err=True)

    click.echo()
    _info("Writing .projectmind/ …")
    generator = DNAGenerator(dna, llm_summary=llm_summary)
    pm_dir = generator.generate()

    for f in sorted(pm_dir.iterdir()):
        if f.is_file():
            _ok(f.name)

    click.echo()
    click.echo(click.style(f" ProjectMind initialized → {pm_dir}", fg="green", bold=True))
    click.echo()


# ---------------------------------------------------------------------------
# projectmind analyze
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--max-files", default=500, show_default=True, help="Max source files to parse")
@click.option("--no-save", is_flag=True, default=False, help="Skip writing JSON report files")
@click.option("--no-cache", is_flag=True, default=False, help="Disable incremental parse cache")
def analyze(path: str, max_files: int, no_save: bool, no_cache: bool):
    """Run static analysis: circular deps, dead code, duplicates, security scan."""
    from backend.core.analyzer.ast_parser import ProjectParser
    from backend.core.analyzer.dead_code import DeadCodeDetector
    from backend.core.analyzer.dependency import DependencyAnalyzer
    from backend.core.analyzer.duplicates import DuplicateDetector
    from backend.core.analyzer.reporter import Reporter
    from backend.core.analyzer.security import SecurityScanner

    root = Path(path).resolve()
    _header(f"Analyzing  {root.name}")

    cache = None
    if not no_cache:
        from backend.core.analyzer.cache import AnalysisCache
        cache_path = root / ".projectmind" / "analysis_cache.json"
        cache = AnalysisCache(cache_path)

    _info("Parsing source files …")
    analyses = ProjectParser(str(root)).parse(max_files=max_files, cache=cache)
    ok = [a for a in analyses if not a.parse_error]

    if cache:
        s = cache.stats
        hit_info = f"  cache {s['hit_rate_pct']}% hit  ({s['hits']} cached / {s['misses']} parsed)"
        _ok(f"Parsed {len(ok)}/{len(analyses)} files{hit_info}")
    else:
        _ok(f"Parsed {len(ok)}/{len(analyses)} files")

    _info("Building dependency graph …")
    dep = DependencyAnalyzer(str(root), analyses).analyze()

    _info("Detecting duplicates …")
    dup = DuplicateDetector(analyses).detect()

    _info("Detecting dead code …")
    dead = DeadCodeDetector(analyses).detect()

    _info("Running security scan …")
    security = SecurityScanner(str(root)).scan([a.path for a in ok])

    reporter = Reporter(
        project_root=str(root),
        language="python",
        file_analyses=analyses,
        dep_report=dep,
        dup_report=dup,
        dead_report=dead,
        security_issues=security,
    )
    report = reporter.build()
    report.print_summary()

    if not no_save:
        rp, hp = reporter.save(report)
        _ok(f"Report   → {rp.relative_to(root)}")
        _ok(f"Health   → {hp.relative_to(root)}")
    else:
        _warn("--no-save: JSON files not written")
    click.echo()


# ---------------------------------------------------------------------------
# projectmind serve
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--port", default=8000, show_default=True, help="Port to bind")
@click.option("--reload/--no-reload", default=True, show_default=True)
def serve(port: int, reload: bool):
    """Start the ProjectMind FastAPI backend."""
    import uvicorn
    click.echo(f"🚀 Starting ProjectMind API on port {port}")
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=port, reload=reload)


# ---------------------------------------------------------------------------
# projectmind memory
# ---------------------------------------------------------------------------

@cli.group()
def memory():
    """Manage project memory (tasks, errors, decisions, patterns)."""


def _resolve_db(project_path: str) -> str:
    db = Path(project_path) / ".projectmind" / "memory.db"
    if not db.exists():
        click.echo(f"❌ No memory.db at {db}. Run `projectmind init` first.", err=True)
        sys.exit(1)
    return str(db)


@memory.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--type", "mem_type", default="all", type=click.Choice(["all", "tasks", "errors", "decisions", "patterns"]))
def memory_list(path: str, mem_type: str):
    """List stored memories for a project."""
    from backend.core.memory.store import MemoryStore

    project_path = str(Path(path).resolve())
    db_path = _resolve_db(project_path)
    store = MemoryStore(db_path)
    store.init_db()

    if mem_type in ("all", "tasks"):
        tasks = store.list_tasks(project_path)
        click.echo(f"\n📋 Tasks ({len(tasks)}):")
        for t in tasks:
            click.echo(f"  [{t.status}] {t.name}")

    if mem_type in ("all", "errors"):
        errors = store.list_errors(project_path)
        click.echo(f"\n🐛 Known Errors ({len(errors)}):")
        for e in errors:
            click.echo(f"  [{e.confidence:.0%}] {e.error[:80]}")

    if mem_type in ("all", "decisions"):
        decisions = store.list_decisions(project_path)
        click.echo(f"\n🧠 Decisions ({len(decisions)}):")
        for d in decisions:
            click.echo(f"  • {d.decision}")

    if mem_type in ("all", "patterns"):
        patterns = store.list_patterns(project_path)
        click.echo(f"\n🔁 Patterns ({len(patterns)}):")
        for p in patterns:
            click.echo(f"  [{p.category}] {p.name}")

    # Token savings banner
    try:
        from backend.core.token_stats import TokenStats
        pm_dir = Path(path).resolve() / ".projectmind"
        if pm_dir.exists():
            s = TokenStats(pm_dir).summary()
            if s["total_calls"] > 0:
                month = s["this_month"]
                cost = month["estimated_cost_saved_usd"]
                saved = month["tokens_saved"]
                def _fmt(n: int) -> str:
                    return f"{n/1_000_000:.1f}M" if n >= 1_000_000 else f"{n/1_000:.0f}K" if n >= 1_000 else str(n)
                click.echo()
                click.echo(
                    click.style(f"  Token savings this month: ", fg="bright_black") +
                    click.style(f"{_fmt(saved)} tokens saved", fg="green", bold=True) +
                    click.style(f"  (~${cost:.2f} at GPT-4o pricing)  ", fg="yellow") +
                    click.style("  `projectmind memory stats` for details", fg="bright_black")
                )
    except Exception:
        pass


@memory.command("add-decision")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--decision", prompt=True)
@click.option("--reason", prompt=True)
def memory_add_decision(path: str, decision: str, reason: str):
    """Record an architectural decision."""
    from backend.core.memory.store import MemoryStore

    project_path = str(Path(path).resolve())
    db_path = _resolve_db(project_path)
    store = MemoryStore(db_path)
    store.init_db()
    record = store.add_decision(project_path, decision, reason)
    click.echo(f"✅ Decision #{record.id} recorded.")


@memory.command("add-error")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--error", prompt=True)
@click.option("--fix", prompt=True)
@click.option("--confidence", default=0.5, type=float)
def memory_add_error(path: str, error: str, fix: str, confidence: float):
    """Record a known error and its fix."""
    from backend.core.memory.store import MemoryStore

    project_path = str(Path(path).resolve())
    db_path = _resolve_db(project_path)
    store = MemoryStore(db_path)
    store.init_db()
    record = store.add_error(project_path, error, fix, confidence)
    click.echo(f"✅ Error #{record.id} recorded (confidence: {record.confidence:.0%}).")


# ---------------------------------------------------------------------------
# projectmind compress
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", default=None, help="Write JSON to file instead of stdout")
@click.option("--budget", default=6000, show_default=True, help="Token budget")
@click.option("--show-text", is_flag=True, default=False, help="Also print the assembled context text")
def compress(path: str, output: str | None, budget: int, show_text: bool):
    """Compress project context into a token-efficient JSON summary (no LLM required)."""
    from backend.core.compression.compressor import Compressor
    from backend.core.compression.budget import coding_agent_budget

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        click.echo("❌ Run `projectmind init` first.", err=True)
        sys.exit(1)

    click.echo(f"\n🗜️  Compressing context for: {root.name}")
    try:
        compressor = Compressor(str(root))
        b = coding_agent_budget(budget)
        result = compressor.compress_with_budget(b)
    except Exception as e:
        click.echo(f"❌ Compression failed: {e}", err=True)
        sys.exit(1)

    ctx_json = json.dumps(result["context_json"], indent=2)
    usage = result["budget"]

    click.echo(f"  Token budget : {usage['total_budget']:,}")
    click.echo(f"  Tokens used  : {usage['used']:,} ({usage['utilisation_pct']}%)")
    click.echo(f"  Remaining    : {usage['remaining']:,}")

    if show_text:
        click.echo("\n" + "─" * 60)
        click.echo(result["assembled_text"])
        click.echo("─" * 60)

    if output:
        Path(output).write_text(ctx_json)
        click.echo(f"\n✅ Compressed context written to {output}")
    else:
        click.echo("\n" + ctx_json)


# ---------------------------------------------------------------------------
# projectmind generate-prompt
# ---------------------------------------------------------------------------

@cli.command("generate-prompt")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--task", prompt="Task description", help="What you want the coding agent to do")
@click.option("--output", default=None, help="Write prompt to file instead of stdout")
@click.option("--llm", is_flag=True, default=False, help="Enhance with LLM (requires API key)")
@click.option("--api-key", envvar="API_KEY", default=None)
@click.option("--provider", default="openai", type=click.Choice(["openai", "ollama", "anthropic", "nvidia"]))
@click.option("--memories", default=5, show_default=True, help="Number of relevant memories to include")
def generate_prompt(
    path: str,
    task: str,
    output: str | None,
    llm: bool,
    api_key: str | None,
    provider: str,
    memories: int,
):
    """Generate a context-enriched prompt for a coding agent."""
    from backend.core.prompt.generator import SmartPromptGenerator

    root = Path(path).resolve()
    if not (root / ".projectmind").exists():
        click.echo("❌ Run `projectmind init` first.", err=True)
        sys.exit(1)

    click.echo(f"\n✨ Generating prompt for: {root.name}")
    click.echo(f"   Task: {task}\n")

    try:
        gen = SmartPromptGenerator(str(root))
        result = gen.generate(
            task=task,
            llm_enhance=llm,
            llm_provider=provider,
            api_key=api_key,
            k_memories=memories,
        )
    except Exception as e:
        click.echo(f"❌ Generation failed: {e}", err=True)
        sys.exit(1)

    usage = result["budget"]
    click.echo(f"  Tokens used  : {usage['used']:,} / {usage['total_budget']:,}")
    if result["relevant_memories"]:
        click.echo(f"  Memories     : {len(result['relevant_memories'])} relevant items found")

    prompt_text = result["prompt"]

    if output:
        Path(output).write_text(prompt_text)
        click.echo(f"\n✅ Prompt written to {output}")
    else:
        click.echo("\n" + "═" * 60)
        click.echo(prompt_text)
        click.echo("═" * 60)


# ---------------------------------------------------------------------------
# projectmind graph
# ---------------------------------------------------------------------------

@cli.group()
def graph():
    """Build and query the project knowledge graph."""


@graph.command("build")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--max-files", default=500, show_default=True)
@click.option("--no-save", is_flag=True, default=False)
def graph_build(path: str, max_files: int, no_save: bool):
    """Parse the project and build a file/function/class dependency graph."""
    from backend.core.analyzer.ast_parser import ProjectParser
    from backend.core.graph.builder import GraphBuilder
    from backend.core.graph.queries import GraphQueries
    from backend.core.graph.serializer import GraphSerializer

    root = Path(path).resolve()
    click.echo(f"\n🕸️  Building knowledge graph for: {root.name}\n")

    click.echo("  Parsing source files …")
    analyses = ProjectParser(str(root)).parse(max_files=max_files)
    ok = [a for a in analyses if not a.parse_error]
    click.echo(f"  Parsed {len(ok)}/{len(analyses)} files")

    click.echo("  Building graph …")
    graph_obj = GraphBuilder(str(root)).build(analyses)
    q = GraphQueries(graph_obj, str(root))
    summary = q.summary()

    click.echo(f"\n  Nodes  : {summary['nodes']['total']} "
               f"({summary['nodes']['files']} files, "
               f"{summary['nodes']['functions']} functions, "
               f"{summary['nodes']['classes']} classes)")
    click.echo(f"  Edges  : {summary['edges']['total']}")
    click.echo(f"  Cycles : {'yes ⚠️' if summary['has_cycles'] else 'none ✓'}")
    click.echo(f"  Components: {summary['components']}")

    if not no_save:
        out = root / ".projectmind" / "knowledge_graph" / "graph.json"
        GraphSerializer().save(graph_obj, out)
        click.echo(f"\n✅ Graph saved to {out.relative_to(root)}")

    click.echo("\n  Most critical files (by PageRank):")
    for i, entry in enumerate(q.most_central(top_n=5), 1):
        click.echo(f"  {i}. {entry['file']}  (score: {entry['centrality_score']})")


@graph.command("impact")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--file", "target_file", required=True, help="File to analyse (relative path)")
def graph_impact(path: str, target_file: str):
    """Show all files that would break if the given file changes."""
    from backend.core.graph.queries import GraphQueries
    from backend.core.graph.serializer import GraphSerializer

    root = Path(path).resolve()
    graph_file = root / ".projectmind" / "knowledge_graph" / "graph.json"
    if not graph_file.exists():
        click.echo("❌ Run `projectmind graph build` first.", err=True)
        sys.exit(1)

    g = GraphSerializer().load(graph_file)
    q = GraphQueries(g, str(root))
    result = q.impact_of(target_file)

    affected = result["affected_files"]
    click.echo(f"\n🎯 Impact of changing: {target_file}")
    click.echo(f"   {len(affected)} file(s) affected (max depth: {result['depth']})\n")
    for f in sorted(affected):
        click.echo(f"  → {f}")
    if not affected:
        click.echo("  No other files depend on this one.")


@graph.command("who-needs")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--file", "target_file", required=True, help="File to inspect")
def graph_who_needs(path: str, target_file: str):
    """Show every file that imports or references the given file."""
    from backend.core.graph.queries import GraphQueries
    from backend.core.graph.serializer import GraphSerializer

    root = Path(path).resolve()
    graph_file = root / ".projectmind" / "knowledge_graph" / "graph.json"
    if not graph_file.exists():
        click.echo("❌ Run `projectmind graph build` first.", err=True)
        sys.exit(1)

    g = GraphSerializer().load(graph_file)
    q = GraphQueries(g, str(root))
    dependents = q.dependents_of(target_file)

    click.echo(f"\n👥 Files that depend on: {target_file}")
    click.echo(f"   {len(dependents)} file(s)\n")
    for f in dependents:
        click.echo(f"  ← {f}")
    if not dependents:
        click.echo("  Nothing depends on this file.")


@graph.command("deps")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--file", "target_file", required=True, help="File to inspect")
def graph_deps(path: str, target_file: str):
    """Show what a file depends on (direct + transitive)."""
    from backend.core.graph.queries import GraphQueries
    from backend.core.graph.serializer import GraphSerializer

    root = Path(path).resolve()
    graph_file = root / ".projectmind" / "knowledge_graph" / "graph.json"
    if not graph_file.exists():
        click.echo("❌ Run `projectmind graph build` first.", err=True)
        sys.exit(1)

    g = GraphSerializer().load(graph_file)
    q = GraphQueries(g, str(root))
    result = q.dependencies_of(target_file)

    click.echo(f"\n📦 Dependencies of: {target_file}")
    click.echo(f"\n  Direct ({len(result['direct'])}):")
    for f in result["direct"]:
        click.echo(f"    {f}")
    click.echo(f"\n  Transitive ({len(result['transitive'])}):")
    for f in result["transitive"]:
        click.echo(f"    {f}")


# ---------------------------------------------------------------------------
# projectmind memory search
# ---------------------------------------------------------------------------

@memory.command("search")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--query", prompt="Search query")
@click.option("--k", default=5, show_default=True, help="Number of results")
@click.option("--type", "mem_type", default=None,
              type=click.Choice(["tasks", "errors", "decisions", "patterns"]),
              help="Filter to a single memory type")
def memory_search(path: str, query: str, k: int, mem_type: str | None):
    """Semantic search across project memories."""
    from backend.core.memory.store import MemoryStore

    project_path = str(Path(path).resolve())
    db_path = _resolve_db(project_path)
    store = MemoryStore(db_path, enable_vectors=True)
    store.init_db()

    types = [mem_type] if mem_type else None
    results = store.search(query, k=k, memory_types=types)

    if not results:
        click.echo("No relevant memories found.")
        return

    click.echo(f"\nFound {len(results)} result(s) for: '{query}'\n")
    for i, r in enumerate(results, 1):
        score = f"  (score: {r['score']:.3f})" if r.get("score") else ""
        click.echo(f"{i}. [{r['type']}]{score}")
        click.echo(f"   {r['content'][:200]}")
        click.echo()


# ---------------------------------------------------------------------------
# projectmind export
# ---------------------------------------------------------------------------

@cli.command("export")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option(
    "--format", "fmt",
    default="claude-md",
    type=click.Choice(["claude-md", "cursorrules", "windsurfrules"]),
    show_default=True,
    help="Output format",
)
@click.option("--print", "print_output", is_flag=True, default=False, help="Also print to stdout")
def export_context(path: str, fmt: str, print_output: bool):
    """Export compressed context as CLAUDE.md, .cursorrules, or .windsurfrules."""
    from backend.core.compression.exporter import export

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header(f"Exporting  {root.name}  →  {fmt}")

    try:
        out_path, content = export(str(root), fmt)
    except Exception as e:
        _err(f"Export failed: {e}")
        sys.exit(1)

    tokens = len(content) // 4
    _ok(f"Written to  {out_path.relative_to(root)}  (~{tokens:,} tokens)")

    if print_output:
        click.echo("\n" + "─" * 60)
        click.echo(content)
        click.echo("─" * 60)
    else:
        click.echo()
        click.echo(click.style(f" {out_path}", fg="green"))
    click.echo()


# ---------------------------------------------------------------------------
# projectmind watch
# ---------------------------------------------------------------------------

@cli.command("watch")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--debounce", default=2.0, show_default=True,
              help="Seconds of inactivity before re-analysis triggers")
def watch(path: str, debounce: float):
    """Watch for file changes and auto-update .projectmind/ context."""
    from backend.core.watcher.watcher import ProjectWatcher

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"

    _header(f"Watching  {root.name}")

    if not pm_dir.exists():
        _warn(".projectmind/ not found — running init first …")
        from backend.core.dna.extractor import DNAExtractor
        from backend.core.dna.generator import DNAGenerator
        dna = DNAExtractor(str(root)).extract()
        DNAGenerator(dna).generate()
        _ok("Initialized .projectmind/")

    def _on_update(msg: str) -> None:
        ts = click.style(__import__("datetime").datetime.now().strftime("%H:%M:%S"), fg="bright_black")
        if msg.startswith("Watching"):
            click.echo(f"\n{click.style('  ◉', fg='green', bold=True)}  {msg}")
            click.echo(click.style("  Press Ctrl+C to stop.\n", fg="bright_black"))
        elif "error" in msg.lower():
            click.echo(f"  {ts}  {click.style(msg, fg='red')}")
        elif msg.startswith("  DNA"):
            click.echo(f"  {ts}  {click.style(msg.strip(), fg='cyan')}")
        elif msg.startswith("  Graph"):
            click.echo(f"  {ts}  {click.style(msg.strip(), fg='yellow')}")
        elif msg.startswith("  Health"):
            click.echo(f"  {ts}  {click.style(msg.strip(), fg='green')}")
        elif msg.startswith("["):
            # Change event header
            click.echo(f"\n  {ts}  {click.style('change detected', fg='bright_white', bold=True)}: {msg.split(' ', 1)[-1]}")
        else:
            click.echo(f"  {ts}  {msg}")

    watcher = ProjectWatcher(str(root), debounce=debounce, on_update=_on_update)
    watcher.start(block=True)


# ---------------------------------------------------------------------------
# projectmind review
# ---------------------------------------------------------------------------

@cli.command("review")
@click.option("--platform", default="github",
              type=click.Choice(["github", "gitlab"]), show_default=True)
@click.option("--token", envvar="GIT_TOKEN", required=True,
              help="GitHub personal access token (or set GIT_TOKEN)")
@click.option("--owner", default=None, help="GitHub owner / org (GitHub only)")
@click.option("--repo", default=None, help="GitHub repo name (GitHub only)")
@click.option("--pr", "pr_number", default=None, type=int, help="PR number (GitHub only)")
@click.option("--project-id", default=None, help="GitLab project ID (GitLab only)")
@click.option("--mr", "mr_iid", default=None, type=int, help="MR iid (GitLab only)")
@click.option("--post", is_flag=True, default=False, help="Post review as a PR/MR comment")
@click.option("--provider", default=None, envvar="LLM_PROVIDER",
              type=click.Choice(["openai", "ollama", "anthropic", "nvidia"]))
@click.option("--api-key", envvar="API_KEY", default=None)
@click.option("--model", default=None, envvar="CODE_MODEL")
def review(
    platform: str, token: str,
    owner: str | None, repo: str | None, pr_number: int | None,
    project_id: str | None, mr_iid: int | None,
    post: bool, provider: str | None, api_key: str | None, model: str | None,
):
    """Run an AI code review on a GitHub PR or GitLab MR."""
    import httpx

    _header(f"Reviewing  {platform.upper()} PR/MR")

    # Validate required fields
    if platform == "github" and not all([owner, repo, pr_number]):
        _err("GitHub review requires --owner, --repo, and --pr")
        sys.exit(1)
    if platform == "gitlab" and not all([project_id, mr_iid]):
        _err("GitLab review requires --project-id and --mr")
        sys.exit(1)

    payload: dict = {
        "git_token": token,
        "platform": platform,
        "post_comment": post,
        "llm_provider": provider or "openai",
    }
    if api_key:
        payload["api_key"] = api_key
    if model:
        payload["code_model"] = model
        payload["conversation_model"] = model

    if platform == "github":
        payload.update({"owner": owner, "repo": repo, "pr_number": pr_number})
        _info(f"PR: {owner}/{repo}#{pr_number}")
    else:
        payload.update({"project_id": project_id, "merge_request_iid": mr_iid})
        _info(f"MR: {project_id}!{mr_iid}")

    api_url = os.environ.get("PROJECTMIND_API_URL", "http://localhost:8000")

    try:
        _info("Calling review chain …")
        resp = httpx.post(f"{api_url}/review", json=payload, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        _err(f"API error {e.response.status_code}: {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:
        _err(f"Request failed: {e}")
        sys.exit(1)

    data = resp.json()
    click.echo()
    click.echo(click.style(" Review Result", fg="bright_white", bold=True))
    click.echo(click.style(" " + "─" * 60, fg="bright_black"))
    click.echo(data["content"])
    click.echo(click.style(" " + "─" * 60, fg="bright_black"))

    if data.get("posted_comment"):
        _ok("Comment posted to PR/MR")
    if data.get("pr_info"):
        info = data["pr_info"]
        _info(f"{info.get('title', '')}  (+{info.get('additions',0)} / -{info.get('deletions',0)})")
    click.echo()


# ---------------------------------------------------------------------------
# projectmind memory stats  (token savings dashboard)
# ---------------------------------------------------------------------------

@memory.command("stats")
@click.argument("path", default=".", type=click.Path(exists=True))
def memory_stats(path: str):
    """Show cumulative token savings and estimated cost avoided."""
    from backend.core.token_stats import TokenStats

    pm_dir = Path(path).resolve() / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    stats = TokenStats(pm_dir)
    s = stats.summary()

    _header("Token Savings Dashboard")

    total_saved = s["total_tokens_saved"]
    cost_saved  = s["estimated_cost_saved_usd"]
    raw_tokens  = s["raw_codebase_tokens"]
    compression = s["avg_compression_pct"]
    calls       = s["total_calls"]

    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000:     return f"{n/1_000:.1f}K"
        return str(n)

    click.echo()
    click.echo(
        f"  {click.style(_fmt_tokens(total_saved), fg='green', bold=True)} tokens saved  "
        f"  {click.style(f'~${cost_saved:.2f}', fg='yellow', bold=True)} avoided  "
        f"(at GPT-4o pricing)"
    )
    click.echo()
    _info(f"Total calls          {calls:,}")
    _info(f"Raw codebase size    ~{_fmt_tokens(raw_tokens)} tokens / run")
    _info(f"Avg compression      {compression}%")
    _info(f"Total tokens used    {_fmt_tokens(s['total_tokens_used'])}")

    month = s["this_month"]
    if month["calls"] > 0:
        click.echo()
        click.echo(click.style("  This month", fg="bright_white", bold=True))
        _info(f"Calls                {month['calls']:,}")
        _info(f"Tokens saved         {_fmt_tokens(month['tokens_saved'])}")
        _info(f"Est. cost avoided    ~${month['estimated_cost_saved_usd']:.2f}")

    by_tool = s.get("by_tool", {})
    if by_tool:
        click.echo()
        click.echo(click.style("  By Tool", fg="bright_white", bold=True))
        for tool, d in sorted(by_tool.items(), key=lambda x: -x[1]["tokens_saved"]):
            _info(f"{tool:<20} {d['calls']:>4} calls   {_fmt_tokens(d['tokens_saved'])} saved")

    click.echo()


# ---------------------------------------------------------------------------
# projectmind diff
# ---------------------------------------------------------------------------

@cli.command("diff")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--against", default=None, metavar="GIT_REF",
              help="Git ref to compare against (branch, commit, tag). "
                   "Omit to compare latest vs previous snapshot.")
def diff(path: str, against: str | None):
    """Compare health scores — spot regressions before they merge."""
    from backend.core.diff.snapshots import load_latest, load_previous
    from backend.core.diff.comparator import compare, analyze_ref, DiffReport

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header("Health Diff")

    # ── fetch before / after ──────────────────────────────────────────────
    if against:
        _info(f"Analyzing ref  {against}  (this may take a moment) …")
        try:
            before_snap = analyze_ref(root, against)
        except RuntimeError as e:
            _err(str(e))
            sys.exit(1)
        after_snap = load_latest(pm_dir)
        if after_snap is None:
            _err("No current snapshot. Run `projectmind analyze` first.")
            sys.exit(1)
        before_label = against
        after_label  = after_snap.get("git", {}).get("branch", "current")
    else:
        after_snap  = load_latest(pm_dir)
        before_snap = load_previous(pm_dir)
        if after_snap is None:
            _err("No snapshots found. Run `projectmind analyze` at least once.")
            sys.exit(1)
        if before_snap is None:
            _err("Only one snapshot found. Run `projectmind analyze` again after making changes.")
            sys.exit(1)
        before_label = before_snap.get("git", {}).get("commit", "previous")
        after_label  = after_snap.get("git", {}).get("branch", "current")
        _info(f"Comparing  {before_label}  →  {after_label}")

    assert before_snap is not None and after_snap is not None
    report = compare(before_snap, after_snap, before_label, after_label)

    # ── render ────────────────────────────────────────────────────────────
    click.echo()

    # Score table
    col_w = 18
    click.echo(click.style(f"  {'Dimension':<{col_w}} {'Before':>7}   {'After':>7}   {'Change':>8}", fg="bright_black"))
    click.echo(click.style("  " + "─" * 50, fg="bright_black"))

    for sc in report.scores:
        arrow = "▲" if sc.direction == "up" else ("▼" if sc.direction == "down" else "=")
        delta_str = f"{sc.delta:+.1f}"
        color = "green" if sc.direction == "up" else ("red" if sc.direction == "down" else "bright_black")
        flag = "  ✗" if (sc.name == "Security" and sc.delta < -1.5) else \
               ("  ⚠" if sc.direction == "down" and sc.delta < -0.5 else "")
        click.echo(
            f"  {sc.name:<{col_w}} "
            f"{sc.before:>6.1f}   "
            f"{sc.after:>6.1f}   "
            f"{click.style(f'{arrow} {delta_str}', fg=color):>12}"
            f"{click.style(flag, fg='red')}"
        )

    # Issue changes
    changed_issues = [i for i in report.issues if i.delta != 0]
    if changed_issues:
        click.echo()
        click.echo(click.style("  Issue Changes", fg="bright_white", bold=True))
        click.echo(click.style("  " + "─" * 50, fg="bright_black"))
        for iss in changed_issues:
            sign = "+" if iss.delta > 0 else ""
            color = "red" if iss.delta > 0 else "green"
            click.echo(
                f"  {iss.name:<28} "
                f"{iss.before:>4} → {iss.after:<4}  "
                f"{click.style(f'{sign}{iss.delta}', fg=color)}"
            )

    # Verdict
    click.echo()
    verdict_color = {"improved": "green", "degraded": "red", "unchanged": "bright_black"}[report.verdict]
    click.echo(
        f"  {click.style('Verdict:', fg='bright_white', bold=True)}  "
        f"{click.style(report.verdict_detail, fg=verdict_color)}"
    )
    click.echo()

    if report.verdict == "degraded":
        sys.exit(1)   # non-zero exit for CI gates


# ---------------------------------------------------------------------------
# projectmind ask
# ---------------------------------------------------------------------------

@cli.command("ask")
@click.argument("question")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--provider", default=None, envvar="LLM_PROVIDER",
              type=click.Choice(["openai", "nvidia", "anthropic", "ollama"]))
@click.option("--api-key", envvar="API_KEY", default=None)
@click.option("--model", default=None, envvar="CODE_MODEL")
def ask(question: str, path: str, provider: str | None, api_key: str | None, model: str | None):
    """Ask the AI Architect Advisor a question about your codebase.

    Examples:

      projectmind ask "Can this scale to 1M users?"

      projectmind ask "Should I migrate to microservices?"

      projectmind ask "What are the biggest risks in this codebase?"
    """
    from backend.core.advisor.advisor import ArchitectAdvisor

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header("AI Architect Advisor")
    _info(f"Question:  {question}")
    click.echo()
    _info("Thinking …")

    try:
        advisor = ArchitectAdvisor(str(root))
        result = advisor.ask(
            question=question,
            llm_provider=provider or os.environ.get("LLM_PROVIDER", "openai"),
            model=model,
            api_key=api_key,
        )
    except Exception as e:
        _err(f"Advisor failed: {e}")
        sys.exit(1)

    click.echo()
    click.echo(click.style(" ─" * 35, fg="bright_black"))
    click.echo()
    click.echo(result["answer"])
    click.echo()
    click.echo(click.style(" ─" * 35, fg="bright_black"))
    _info(f"Context used: ~{result['context_tokens']} tokens  (vs ~{_estimate_raw(root)} raw)")
    click.echo()


def _estimate_raw(root: Path) -> str:
    try:
        from backend.core.token_stats import estimate_raw_tokens
        n = estimate_raw_tokens(root)
        return f"{n//1000}K tokens" if n >= 1000 else f"{n} tokens"
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# projectmind session
# ---------------------------------------------------------------------------

@cli.group("session")
def session():
    """Manage AI coding sessions — continuity between conversations."""


@session.command("status")
@click.argument("path", default=".", type=click.Path(exists=True))
def session_status(path: str):
    """Show the current or last session for a project."""
    from backend.core.session.tracker import SessionTracker

    pm_dir = Path(path).resolve() / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    tracker = SessionTracker(pm_dir)
    active = tracker.get_active()
    last = tracker.get_last_completed()

    _header("Session Status")
    click.echo()

    if active:
        age = int(active.age_minutes())
        click.echo(click.style("  Active session", fg="green", bold=True))
        _info(f"Task        {active.task}")
        _info(f"Started     {active.started_at[:19].replace('T', ' ')} UTC  ({age} min ago)")
        _info(f"Session ID  {active.session_id}")
        if active.files_modified:
            _info(f"Modified    {', '.join(active.files_modified[:6])}")
        if active.uncommitted_files:
            _warn(f"Uncommitted {', '.join(active.uncommitted_files[:5])}")
    else:
        click.echo(click.style("  No active session", fg="bright_black"))

    if last:
        click.echo()
        click.echo(click.style("  Last session", fg="bright_white", bold=True))
        _info(f"Task        {last.task}")
        _info(f"Duration    {int(last.duration_minutes())} min")
        _info(f"Status      {last.status}")
        if last.files_modified:
            _info(f"Modified    {', '.join(last.files_modified[:6])}")
        if last.uncommitted_files and last.status != "ended":
            _warn(f"Left uncommitted: {', '.join(last.uncommitted_files[:5])}")
    click.echo()


@session.command("end")
@click.argument("path", default=".", type=click.Path(exists=True))
def session_end(path: str):
    """Mark the current session as ended."""
    from backend.core.session.tracker import SessionTracker

    pm_dir = Path(path).resolve() / ".projectmind"
    if not pm_dir.exists():
        _err("No .projectmind/ found.")
        sys.exit(1)

    tracker = SessionTracker(pm_dir)
    s = tracker.end_session("ended")
    if s:
        _ok(f"Session {s.session_id} ended. Modified {len(s.files_modified)} files.")
    else:
        _warn("No active session found.")


@session.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--limit", default=5, type=int)
def session_list(path: str, limit: int):
    """List recent sessions."""
    from backend.core.session.tracker import SessionTracker

    pm_dir = Path(path).resolve() / ".projectmind"
    hist_dir = pm_dir / "sessions"

    if not hist_dir.exists():
        _info("No session history found.")
        return

    files = sorted(hist_dir.glob("*.json"), reverse=True)[:limit]
    if not files:
        _info("No completed sessions yet.")
        return

    _header("Recent Sessions")
    click.echo()
    for f in files:
        try:
            from backend.core.session.tracker import SessionState
            data = json.loads(f.read_text())
            s = SessionState(**data)
            icon = "✓" if s.status == "ended" else "⚠"
            color = "green" if s.status == "ended" else "yellow"
            click.echo(
                f"  {click.style(icon, fg=color)}  "
                f"{s.started_at[:10]}  "
                f"{click.style(s.task[:60], fg='bright_white')}  "
                f"({int(s.duration_minutes())} min, {len(s.files_modified)} files)"
            )
        except Exception:
            pass
    click.echo()


# ---------------------------------------------------------------------------
# projectmind deps
# ---------------------------------------------------------------------------

@cli.group("deps")
def deps():
    """Dependency risk scoring — CVEs, staleness, and import centrality."""


@deps.command("risk")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--min-level", default="LOW",
              type=click.Choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
              help="Only show deps at or above this risk level")
@click.option("--limit", default=30, type=int)
@click.option("--json", "output_json", is_flag=True, default=False)
def deps_risk(path: str, min_level: str, limit: int, output_json: bool):
    """Scan dependencies and rank them by security risk.

    Queries PyPI / npm metadata and the OSV vulnerability database.
    No API key required.
    """
    from backend.core.deps.risk import score_dependencies

    root = Path(path).resolve()
    _level_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    min_rank = _level_rank[min_level]

    _header("Dependency Risk Scan")
    _info("Fetching metadata from PyPI, npm, and OSV…")
    click.echo()

    try:
        results = score_dependencies(root)
    except Exception as e:
        _err(f"Scan failed: {e}")
        sys.exit(1)

    filtered = [r for r in results if _level_rank.get(r.risk_level, 0) >= min_rank][:limit]

    if output_json:
        import dataclasses
        click.echo(json.dumps([dataclasses.asdict(r) for r in filtered], indent=2))
        return

    if not filtered:
        _ok(f"No dependencies at {min_level}+ risk level.")
        return

    _level_color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "cyan", "LOW": "bright_black"}

    for r in filtered:
        color = _level_color.get(r.risk_level, "white")
        badge = click.style(f" {r.risk_level} ", fg="white", bg=color.replace("bright_", ""), bold=True)
        click.echo(
            f"  {badge}  "
            f"{click.style(r.name, fg='bright_white', bold=True):<30} "
            f"(score: {r.risk_score:.0f})"
        )
        if r.cves:
            sev_counts: dict[str, int] = {}
            for cve in r.cves:
                sev_counts[cve.severity] = sev_counts.get(cve.severity, 0) + 1
            cve_str = "  ".join(f"{k}: {v}" for k, v in sorted(sev_counts.items()))
            click.echo(f"         CVEs: {cve_str}")
        if r.is_stale:
            click.echo(f"         Last release: {r.days_since_release} days ago  ⚠ STALE")
        if r.import_count > 0:
            click.echo(f"         Imported in {r.import_count} file(s)")
        click.echo()

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in results:
        counts[r.risk_level] = counts.get(r.risk_level, 0) + 1
    _info(
        f"Summary: {counts['CRITICAL']} CRITICAL  "
        f"{counts['HIGH']} HIGH  "
        f"{counts['MEDIUM']} MEDIUM  "
        f"{counts['LOW']} LOW  "
        f"({len(results)} total deps scanned)"
    )
    click.echo()


# ---------------------------------------------------------------------------
# projectmind onboard
# ---------------------------------------------------------------------------

@cli.command("onboard")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--for", "role", default="new developer",
              help='Target role, e.g. "new backend engineer", "frontend developer"')
@click.option("--output", default=None, type=click.Path(),
              help="Write guide to a file (default: print to stdout)")
def onboard(path: str, role: str, output: str | None):
    """Generate a role-aware onboarding guide for new developers.

    Produces a sequenced reading list grounded in graph centrality,
    health scores, architectural decisions, and known gotchas.
    No LLM required.

    Example:

      projectmind onboard --for "new backend engineer"
    """
    from backend.core.onboarding.generator import OnboardingGenerator

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header(f"Generating Onboarding Guide — {role}")
    _info("Building from graph centrality + health scores + stored decisions…")

    try:
        gen = OnboardingGenerator(str(root))
        guide = gen.generate(role=role)
    except Exception as e:
        _err(f"Failed: {e}")
        sys.exit(1)

    md = guide.to_markdown()

    if output:
        out_path = Path(output)
        out_path.write_text(md, encoding="utf-8")
        _ok(f"Guide written to {out_path}")
        _info(f"Reading list: {len(guide.reading_list)} files")
        _info(f"Decisions:    {len(guide.key_decisions)}")
        _info(f"Gotchas:      {len(guide.gotchas)}")
    else:
        click.echo()
        click.echo(md)

    click.echo()


# ---------------------------------------------------------------------------
# projectmind changelog
# ---------------------------------------------------------------------------

@cli.command("changelog")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--limit", default=8, type=int, help="Number of snapshots to show")
@click.option("--since", default=None, metavar="GIT_REF",
              help="Only show changes since this git ref")
def changelog(path: str, limit: int, since: str | None):
    """Show what the *architecture* changed — not just which lines.

    Diffs consecutive health snapshots to surface:
      circular deps introduced, security regressions, dead code
      accumulation, complexity spikes, and health score trajectory.

    Snapshots are auto-saved on every `projectmind analyze` run.
    """
    from backend.core.changelog.semantic import build_changelog, format_changelog

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    snaps_dir = pm_dir / "snapshots"
    if not snaps_dir.exists() or not list(snaps_dir.glob("*.json")):
        _err("No snapshots found. Run `projectmind analyze` at least twice.")
        sys.exit(1)

    # Resolve --since to an ISO timestamp using git
    since_ts: str | None = None
    if since:
        import subprocess
        r = subprocess.run(
            ["git", "log", "-1", "--format=%cI", since],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            since_ts = r.stdout.strip()
            _info(f"Showing changes since {since}  ({since_ts[:10]})")
        else:
            _err(f"Could not resolve git ref: {since!r}")
            sys.exit(1)

    try:
        diffs = build_changelog(pm_dir, limit=limit, since_ts=since_ts)
    except Exception as e:
        _err(f"Changelog failed: {e}")
        sys.exit(1)

    if not diffs:
        _warn("Only one snapshot found — need at least 2 to diff. Run `projectmind analyze` again.")
        sys.exit(0)

    _header("Semantic Changelog")
    click.echo()

    _dir_color = {"improved": "green", "degraded": "red", "stable": "bright_black"}
    _dir_icon  = {"improved": "↑",    "degraded": "↓",   "stable": "="}

    for sd in diffs:
        color = _dir_color[sd.direction]
        icon  = _dir_icon[sd.direction]
        delta_str = f"{sd.score_delta:+.1f}"
        header_line = (
            f"  {click.style(icon, fg=color, bold=True)} "
            f"{click.style(sd.timestamp[:10], fg='bright_white')}  "
            f"{click.style(sd.after_commit, fg='cyan')} "
            f"({sd.after_branch})  "
            f"{click.style(f'{sd.overall_before:.1f} → {sd.overall_after:.1f}', fg=color)}  "
            f"{click.style(delta_str, fg=color, bold=True)}"
        )
        click.echo(header_line)

        if sd.events:
            for ev in sd.events:
                ev_color = "green" if "improved" in ev.kind or "resolved" in ev.kind or "decreased" in ev.kind else "red"
                click.echo(
                    f"    {click.style(ev.icon, fg=ev_color)}  "
                    f"{click.style(ev.description, fg='white')}"
                )
        else:
            click.echo(click.style("    =  No significant architectural changes", fg="bright_black"))
        click.echo()

    total_snaps = len(list((pm_dir / "snapshots").glob("*.json")))
    _info(f"{total_snaps} snapshots total — run `projectmind analyze` to add more")
    click.echo()


# ---------------------------------------------------------------------------
# projectmind adr
# ---------------------------------------------------------------------------

@cli.group("adr")
def adr():
    """Manage Architecture Decision Records (ADRs) in MADR format."""


@adr.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
def adr_list(path: str):
    """List all ADRs in docs/adr/."""
    from backend.core.adr.generator import ADRGenerator

    gen = ADRGenerator(str(Path(path).resolve()))
    adrs = gen.list_adrs()
    _header("Architecture Decision Records")
    click.echo()
    if not adrs:
        _info("No ADRs found. Run `projectmind adr detect` or `projectmind adr create`.")
        return
    for a in adrs:
        click.echo(f"  {click.style(a['file'], fg='cyan')}  {a['title']}  "
                   f"{click.style(a['status'], fg='bright_black')}")
    click.echo()


@adr.command("detect")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--auto-create", is_flag=True, default=False,
              help="Auto-create ADRs for high-confidence detections (≥0.7)")
def adr_detect(path: str, auto_create: bool):
    """Detect changes that warrant an ADR and optionally auto-create them."""
    from backend.core.adr.generator import ADRGenerator, detect_adr_worthy_changes

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header("ADR Detection")
    changes = detect_adr_worthy_changes(pm_dir)
    if not changes:
        _ok("No ADR-worthy changes detected.")
        return

    click.echo()
    gen = ADRGenerator(str(root))
    for c in changes:
        conf_color = "green" if c.auto_confidence >= 0.7 else "yellow" if c.auto_confidence >= 0.5 else "bright_black"
        click.echo(
            f"  {click.style(f'[{c.auto_confidence:.0%}]', fg=conf_color)}  "
            f"{click.style(c.title, fg='bright_white', bold=True)}"
        )
        _info(f"Kind: {c.kind}")
        _info(f"Suggested: {c.suggested_decision}")

        if auto_create and c.auto_confidence >= 0.7:
            out = gen.from_detected(c)
            _ok(f"Created: {out}")
        elif not auto_create and c.auto_confidence >= 0.7:
            _warn("Use --auto-create to generate this ADR automatically")
        click.echo()


@adr.command("create")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--title",    prompt="ADR title")
@click.option("--context",  prompt="Context (why was this decision needed?)")
@click.option("--decision", prompt="Decision (what was decided?)")
@click.option("--status",   default="accepted",
              type=click.Choice(["proposed", "accepted", "deprecated", "superseded"]))
def adr_create(path: str, title: str, context: str, decision: str, status: str):
    """Interactively create a new ADR."""
    from backend.core.adr.generator import ADRGenerator

    gen = ADRGenerator(str(Path(path).resolve()))
    out = gen.create(title=title, context=context, decision=decision, status=status)
    _ok(f"Created {out}")
    _info("Also recorded in project memory — searchable via `projectmind memory search`")
    click.echo()


# ---------------------------------------------------------------------------
# projectmind trace
# ---------------------------------------------------------------------------

@cli.command("trace")
@click.argument("error_text", default="")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--file", "error_file", default=None, type=click.Path(exists=True),
              help="Read error from a file instead of argument")
def trace(error_text: str, path: str, error_file: str | None):
    """Find the root cause of an error using memory + git + graph.

    Paste the error message or stack trace directly:

      projectmind trace "AttributeError: 'NoneType' object has no attribute 'user_id'"

    Or pipe it:

      pytest --tb=short 2>&1 | projectmind trace -
    """
    # Support reading from stdin (pipe) or file
    if error_file:
        error_text = Path(error_file).read_text(encoding="utf-8", errors="ignore")
    elif error_text == "-":
        import sys as _sys
        error_text = _sys.stdin.read()

    if not error_text.strip():
        _err("Provide an error message as argument, --file, or via stdin pipe.")
        sys.exit(1)

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    from backend.core.tracer.tracer import RootCauseTracer

    _header("Root Cause Tracer")
    _info("Analyzing error against memory, git log, and knowledge graph…")
    click.echo()

    try:
        result = RootCauseTracer(str(root)).trace(error_text)
    except Exception as e:
        _err(f"Trace failed: {e}")
        sys.exit(1)

    click.echo(f"  {click.style('Error:', fg='bright_white', bold=True)} {result.error_summary}")
    if result.affected_files:
        click.echo(f"  {click.style('Files:', fg='bright_white')} {', '.join(result.affected_files[:5])}")
    if result.affected_modules:
        click.echo(f"  {click.style('Modules:', fg='bright_white')} {', '.join(result.affected_modules[:5])}")
    click.echo()

    if not result.causes:
        _warn("No probable causes found. Try `projectmind analyze` to build the knowledge graph.")
        return

    click.echo(click.style("  Probable Causes", fg="bright_white", bold=True))
    click.echo(click.style("  " + "─" * 55, fg="bright_black"))

    for cause in result.causes:
        conf_pct = f"{cause.confidence * 100:.0f}%"
        color = "red" if cause.confidence >= 0.8 else "yellow" if cause.confidence >= 0.6 else "bright_black"
        click.echo(
            f"  {click.style(f'#{cause.rank}', fg='bright_black')}  "
            f"{click.style(f'[{conf_pct}]', fg=color, bold=True)}  "
            f"{click.style(cause.description, fg='white')}"
        )
        _info(cause.detail)
        if cause.file:
            _info(f"File: {cause.file}")
        click.echo()

    if result.similar_past_errors:
        click.echo(click.style("  Similar Past Errors", fg="bright_white", bold=True))
        for e in result.similar_past_errors[:2]:
            _info(f"Error: {e['error'][:80]}")
            _info(f"Fix:   {e['fix'][:80]}")
            click.echo()


# ---------------------------------------------------------------------------
# projectmind explain
# ---------------------------------------------------------------------------

@cli.command("explain")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--audience",        default="developer",
              help='Target audience, e.g. "new backend engineer", "open source contributor"')
@click.option("--output",          default=None, type=click.Path(),
              help="Write to a file (default: stdout). Use --output README.md to update your README.")
@click.option("--include-issues",  is_flag=True, default=False,
              help="Include known security issues and circular deps")
@click.option("--llm",             is_flag=True, default=False,
              help="Use LLM to enhance narrative prose (requires API key)")
@click.option("--api-key",         envvar="API_KEY", default=None)
@click.option("--provider",        default="openai",
              type=click.Choice(["openai", "nvidia", "anthropic", "ollama"]))
@click.option("--model",           default=None, envvar="CODE_MODEL")
def explain(
    path: str, audience: str, output: str | None,
    include_issues: bool, llm: bool,
    api_key: str | None, provider: str, model: str | None,
):
    """Generate a grounded README / architecture doc from real analysis data.

    Every fact comes from what ProjectMind actually analyzed — not hallucinated.
    Use --llm to add narrative polish while keeping the facts accurate.

    Examples:

      projectmind explain --output README.md

      projectmind explain --audience "open source contributor" --llm
    """
    from backend.core.explain.generator import ExplainGenerator

    root = Path(path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        _err("Run `projectmind init` first.")
        sys.exit(1)

    _header("Grounded README Generator")
    _info(f"Audience: {audience}  |  LLM enhance: {llm}")
    click.echo()

    try:
        gen = ExplainGenerator(str(root))
        md = gen.generate(
            audience=audience,
            include_issues=include_issues,
            llm_enhance=llm,
            api_key=api_key,
            llm_provider=provider,
            model=model,
        )
    except Exception as e:
        _err(f"Generation failed: {e}")
        sys.exit(1)

    if output:
        out_path = Path(output)
        out_path.write_text(md, encoding="utf-8")
        _ok(f"Written to {out_path}")
        click.echo()
    else:
        click.echo(md)


# ---------------------------------------------------------------------------
# projectmind mcp
# ---------------------------------------------------------------------------

@cli.group("mcp", invoke_without_command=True)
@click.pass_context
def mcp(ctx: click.Context):
    """MCP server management (Claude Code / Cursor / Windsurf integration)."""
    if ctx.invoked_subcommand is None:
        # Backwards-compat: `projectmind mcp` with no subcommand starts the server
        from backend.mcp.server import run
        run()


@mcp.command("start")
def mcp_start():
    """Start the MCP server (stdio transport). Usually called by the MCP host."""
    from backend.mcp.server import run
    run()


@mcp.command("install")
@click.option("--client", default="claude",
              type=click.Choice(["claude", "cursor", "windsurf"]),
              help="Which MCP client to install for")
@click.option("--python", "python_cmd", default=None,
              help="Python executable to use (default: auto-detect)")
def mcp_install(client: str, python_cmd: str | None):
    """Write the correct MCP server config for your AI coding client.

    Detects whether poetry or pip is being used and writes the config
    with the correct absolute path — no manual editing needed.

      projectmind mcp install --client claude
      projectmind mcp install --client cursor
    """
    import subprocess
    import shutil

    repo_root = Path(__file__).resolve().parents[1]

    # Detect how to invoke the MCP server
    if shutil.which("poetry") and (repo_root / "pyproject.toml").exists():
        command = "poetry"
        args = ["run", "projectmind-mcp"]
        cwd = str(repo_root)
    elif python_cmd or shutil.which("projectmind-mcp"):
        command = python_cmd or shutil.which("python3") or "python"
        args = ["-m", "backend.mcp.server"]
        cwd = str(repo_root)
    else:
        command = sys.executable
        args = ["-m", "backend.mcp.server"]
        cwd = str(repo_root)

    server_config = {
        "projectmind": {
            "command": command,
            "args": args,
            "cwd": cwd,
        }
    }

    _header(f"MCP Install — {client}")
    _info(f"Repo root: {cwd}")
    _info(f"Command:   {command} {' '.join(args)}")
    click.echo()

    if client == "claude":
        config_path = Path.home() / ".claude" / "settings.json"
        _write_mcp_to_settings_json(config_path, server_config)
        _ok(f"Written to {config_path}")
        _info("Restart Claude Code to pick up the new MCP server.")

    elif client == "cursor":
        # Cursor uses ~/.cursor/mcp.json
        config_path = Path.home() / ".cursor" / "mcp.json"
        config_path.parent.mkdir(exist_ok=True)
        existing: dict = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass
        existing.setdefault("mcpServers", {}).update(server_config)
        config_path.write_text(json.dumps(existing, indent=2))
        _ok(f"Written to {config_path}")
        _info("Restart Cursor to pick up the new MCP server.")

    elif client == "windsurf":
        # Windsurf uses ~/.codeium/windsurf/mcp_config.json
        config_path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass
        existing.setdefault("mcpServers", {}).update(server_config)
        config_path.write_text(json.dumps(existing, indent=2))
        _ok(f"Written to {config_path}")
        _info("Restart Windsurf to pick up the new MCP server.")

    click.echo()


def _write_mcp_to_settings_json(config_path: Path, server_config: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except Exception:
            pass
    existing.setdefault("mcpServers", {}).update(server_config)
    config_path.write_text(json.dumps(existing, indent=2))


if __name__ == "__main__":
    cli()
