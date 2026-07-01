"""
Grounded README / Architecture Doc Generator.

Unlike LLM-generated docs, every claim here is backed by real analysis data.
The LLM can optionally add narrative prose, but the structure and facts
come from what ProjectMind actually found.

Sections:
  1. Project Overview     — language, frameworks, architecture, entry points
  2. Architecture         — pattern, key files, dependency structure
  3. Getting Started      — how to run, entry points
  4. Core Files           — top N files by PageRank with annotations
  5. Health & Quality     — health scores table + issue summary
  6. Known Issues         — security findings, circular deps (opt-in)
  7. Contributing         — coding conventions, patterns to follow

Usage:
  gen = ExplainGenerator("/path/to/project")
  md = gen.generate(audience="new backend engineer", include_issues=False)
  Path("README.md").write_text(md)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class ExplainGenerator:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.pm_dir = self.root / ".projectmind"

    def generate(
        self,
        audience: str = "developer",
        include_issues: bool = False,
        llm_enhance: bool = False,
        api_key: Optional[str] = None,
        llm_provider: str = "openai",
        model: Optional[str] = None,
    ) -> str:
        ctx     = self._load_context()
        health  = self._load_health()
        report  = self._load_report()
        central = self._load_central_files(top_n=8)
        decisions = self._load_decisions()
        patterns  = self._load_patterns()

        sections: list[str] = []

        # ── Header ────────────────────────────────────────────────────────
        name = self.root.name
        desc = ctx.get("description", "")
        lang = ctx.get("language", "unknown")
        fw   = ctx.get("frameworks", "none")
        db   = ctx.get("database", "none")
        arch = ctx.get("architecture", "unknown")

        sections.append(f"# {name}")
        if desc:
            sections.append(f"\n{desc}\n")

        overall = health.get("overall", "?")
        sec     = health.get("security", "?")
        maint   = health.get("maintainability", "?")
        health_badge = _score_badge(overall if isinstance(overall, (int, float)) else 0)
        sections.append(
            f"![Health {overall}/10]({health_badge}) "
            f"[![Language](https://img.shields.io/badge/language-{lang}-blue)]() "
        )

        # ── Overview ──────────────────────────────────────────────────────
        sections.append("\n## Overview\n")
        sections.append(f"| | |")
        sections.append(f"|---|---|")
        sections.append(f"| **Language** | {lang} |")
        sections.append(f"| **Frameworks** | {fw} |")
        sections.append(f"| **Database** | {db} |")
        sections.append(f"| **Architecture** | {arch} |")
        sections.append(f"| **Health Score** | {overall}/10 |")
        sections.append(f"| **Security** | {sec}/10 |")
        sections.append(f"| **Maintainability** | {maint}/10 |")

        # ── Architecture ──────────────────────────────────────────────────
        sections.append("\n## Architecture\n")
        entry_points = ctx.get("entry_points", [])
        if entry_points:
            sections.append("**Entry Points**\n")
            for ep in entry_points[:5]:
                sections.append(f"- `{ep}`")
        sections.append("")

        if arch:
            sections.append(f"This project follows a **{arch}** architecture.")

        if decisions:
            sections.append("\n**Key Architectural Decisions**\n")
            for d in decisions[:6]:
                sections.append(f"- {d}")

        # ── Getting Started ───────────────────────────────────────────────
        sections.append("\n## Getting Started\n")
        sections.extend(_infer_getting_started(self.root, ctx))

        # ── Core Files ────────────────────────────────────────────────────
        if central:
            sections.append("\n## Core Files\n")
            sections.append("_Files ranked by architectural importance (PageRank centrality)._\n")
            sections.append("| File | Role | Centrality |")
            sections.append("|------|------|------------|")
            for entry in central:
                f = entry.get("file", "")
                score = entry.get("centrality_score", 0)
                role = _infer_role(f)
                sections.append(f"| `{f}` | {role} | {score} |")

        # ── Health & Quality ──────────────────────────────────────────────
        sections.append("\n## Health & Quality\n")
        sections.append("| Dimension | Score |")
        sections.append("|-----------|-------|")
        for dim in ["overall", "architecture", "security", "maintainability", "code_quality"]:
            val = health.get(dim, "?")
            label = dim.replace("_", " ").title()
            icon = "🟢" if isinstance(val, (int, float)) and val >= 7.5 else \
                   "🟡" if isinstance(val, (int, float)) and val >= 5.0 else "🔴"
            sections.append(f"| {icon} {label} | {val}/10 |")

        b = health.get("breakdown", {})
        if b:
            sections.append("")
            sections.append(
                f"Issues: {b.get('security_errors', 0)} security errors · "
                f"{b.get('circular_dependencies', 0)} circular deps · "
                f"{b.get('dead_functions', 0)} dead functions · "
                f"{b.get('high_complexity_functions', 0)} high-complexity functions"
            )

        # ── Known Issues (opt-in) ─────────────────────────────────────────
        if include_issues and report:
            sec_issues = report.get("security_issues", [])
            circ_deps  = report.get("circular_dependencies", [])
            if sec_issues or circ_deps:
                sections.append("\n## Known Issues\n")
                if sec_issues:
                    sections.append("**Security**\n")
                    for i in sec_issues[:5]:
                        sections.append(
                            f"- `{i.get('file', '?')}:{i.get('line', '?')}` — "
                            f"[{i.get('severity', '?').upper()}] {i.get('description', '')}"
                        )
                if circ_deps:
                    sections.append("\n**Circular Dependencies**\n")
                    for c in circ_deps[:3]:
                        sections.append(f"- {' → '.join(c.get('cycle', []))}")

        # ── Contributing ──────────────────────────────────────────────────
        sections.append("\n## Contributing\n")
        conventions = ctx.get("coding_style", [])
        if conventions:
            sections.append("**Coding Conventions**\n")
            for c in conventions[:6]:
                sections.append(f"- {c}")
        if patterns:
            sections.append("\n**Established Patterns**\n")
            for p in patterns[:5]:
                sections.append(f"- {p}")

        sections.append(
            "\n---\n_Documentation generated by "
            "[ProjectMind AI](https://github.com/Aaravkhanal/llm-reviewer) "
            f"— grounded in static analysis, not guessed._"
        )

        md = "\n".join(sections)

        # ── Optional LLM narrative enhancement ───────────────────────────
        if llm_enhance:
            md = self._llm_enhance(md, audience, api_key, llm_provider, model)

        return md

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_context(self) -> dict:
        p = self.pm_dir / "context.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        try:
            from backend.core.compression.compressor import Compressor
            return Compressor(str(self.root)).compress()
        except Exception:
            return {}

    def _load_health(self) -> dict:
        p = self.pm_dir / "health_score.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        return {}

    def _load_report(self) -> dict:
        p = self.pm_dir / "architecture_report.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        return {}

    def _load_central_files(self, top_n: int = 8) -> list[dict]:
        graph_file = self.pm_dir / "knowledge_graph" / "graph.json"
        if not graph_file.exists():
            return []
        try:
            from backend.core.graph.queries import GraphQueries
            from backend.core.graph.serializer import GraphSerializer
            g = GraphSerializer().load(graph_file)
            return GraphQueries(g, str(self.root)).most_central(top_n=top_n)
        except Exception:
            return []

    def _load_decisions(self) -> list[str]:
        db = self.pm_dir / "memory.db"
        if not db.exists():
            return []
        try:
            from backend.core.memory.store import MemoryStore
            store = MemoryStore(str(db))
            store.init_db()
            return [d.decision for d in store.list_decisions(str(self.root))[:8]]
        except Exception:
            return []

    def _load_patterns(self) -> list[str]:
        db = self.pm_dir / "memory.db"
        if not db.exists():
            return []
        try:
            from backend.core.memory.store import MemoryStore
            store = MemoryStore(str(db))
            store.init_db()
            return [f"[{p.category}] {p.name}" for p in store.list_patterns(str(self.root))[:6]]
        except Exception:
            return []

    def _llm_enhance(
        self,
        base_md: str,
        audience: str,
        api_key: Optional[str],
        provider: str,
        model: Optional[str],
    ) -> str:
        import os
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from backend.llm.providers import LLM, LLMProvider

        lm = LLM(
            model_name=model or os.environ.get("CODE_MODEL", "gpt-4o-mini"),
            provider=LLMProvider(provider),
            api_key=api_key,
        )
        assert lm.model is not None
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a technical writer improving a grounded README. "
             "DO NOT change the tables, badges, or file lists — they are factual. "
             "Only improve the prose paragraphs to be clearer and more engaging for "
             f"the target audience: {audience}. "
             "Keep the overall structure and length similar. Return the full markdown."),
            ("human", "{markdown}"),
        ])
        chain = prompt | lm.model | StrOutputParser()
        return chain.invoke({"markdown": base_md})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_badge(score: float) -> str:
    color = "brightgreen" if score >= 7.5 else "yellow" if score >= 5.0 else "red"
    return f"https://img.shields.io/badge/health-{score:.1f}%2F10-{color}"


def _infer_role(file_path: str) -> str:
    lower = file_path.lower()
    hints = [
        ("main",       "Entry point"),
        ("app",        "Application core"),
        ("config",     "Configuration"),
        ("auth",       "Authentication"),
        ("model",      "Data model"),
        ("schema",     "Schema / validation"),
        ("router",     "API routing"),
        ("middleware", "Middleware"),
        ("database",   "Database layer"),
        ("service",    "Business logic"),
        ("util",       "Utilities"),
        ("test",       "Tests"),
        ("agent",      "AI agent"),
        ("graph",      "Knowledge graph"),
    ]
    for kw, label in hints:
        if kw in lower:
            return label
    return "Core module"


def _infer_getting_started(root: Path, ctx: dict) -> list[str]:
    lines: list[str] = []
    lang = ctx.get("language", "").lower()

    # Detect install method
    if (root / "pyproject.toml").exists():
        lines.append("```bash")
        lines.append("# Install dependencies")
        if (root / "poetry.lock").exists():
            lines.append("poetry install")
        else:
            lines.append("pip install -e .")
        lines.append("```\n")
    elif (root / "requirements.txt").exists():
        lines.append("```bash")
        lines.append("pip install -r requirements.txt")
        lines.append("```\n")
    elif (root / "package.json").exists():
        lines.append("```bash")
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else \
             "yarn"  if (root / "yarn.lock").exists() else "npm"
        lines.append(f"{pm} install")
        lines.append("```\n")

    # Entry points
    for ep in ctx.get("entry_points", [])[:3]:
        if ep.endswith(".py"):
            lines.append(f"```bash\npython {ep}\n```\n")
            break
        elif ep.endswith((".ts", ".js")):
            lines.append(f"```bash\nnode {ep}\n```\n")
            break

    # Docker
    if (root / "docker-compose.yml").exists():
        lines.append("```bash\n# Or with Docker\ndocker-compose up\n```\n")

    return lines if lines else ["_See entry points above to run the project._\n"]
