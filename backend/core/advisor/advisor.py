"""
AI Architect Advisor — answers architectural questions about a codebase
using compressed context + graph centrality + health data.

The LLM never reads raw source code.
It works entirely from the ~600-token compressed context built by ProjectMind.

Example questions:
  "Can this scale to 1 million users?"
  "Should I migrate to microservices?"
  "What are the biggest risks in this codebase?"
  "How do I add authentication without breaking the architecture?"
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.core.compression.compressor import Compressor
from backend.llm.providers import LLM, LLMProvider


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a senior software architect reviewing a codebase to answer a specific question.

You have been given compressed intelligence about the project:
- Language, frameworks, and architecture pattern
- The most critical files by PageRank centrality (change these and everything breaks)
- Current health scores (0–10) across architecture, security, maintainability, quality
- Active architectural decisions already made by the team
- Known issues (security findings, dead code, circular dependencies)

Rules:
1. Base your answer on the provided context — do not hallucinate files or patterns not mentioned
2. Reference specific files, scores, or issues from the context when relevant
3. Be direct and opinionated — the team wants a recommendation, not a list of options
4. If the context is insufficient to answer, say exactly what information is missing
5. Keep your answer under 500 words
6. Use markdown formatting (headers, bullet points)
"""

_USER_TEMPLATE = """\
## Project: {project_name}

**Stack:** {language} | {frameworks} | {database}
**Architecture:** {architecture}
**Health:** {overall}/10  (Arch: {arch_score}  Sec: {sec_score}  Maint: {maint_score}  Quality: {quality_score})

## Most Critical Files (PageRank — change these, everything breaks)
{critical_files}

## Active Issues
{issues}

## Architectural Decisions Already Made
{decisions}

## Established Patterns
{patterns}

## Coding Conventions
{conventions}

---

## Question
{question}
"""


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------

class ArchitectAdvisor:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.pm_dir = self.root / ".projectmind"

    def ask(
        self,
        question: str,
        llm_provider: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict:
        """
        Returns:
          {
            "answer": str,
            "context_tokens": int,
            "question": str,
          }
        """
        context = self._build_context()
        provider = LLMProvider(llm_provider)
        lm = LLM(
            model_name=model or os.environ.get("CODE_MODEL", "gpt-4o-mini"),
            provider=provider,
            api_key=api_key,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM),
            ("human", _USER_TEMPLATE),
        ])
        assert lm.model is not None
        chain = prompt | lm.model | StrOutputParser()

        answer = chain.invoke({**context, "question": question})
        context_tokens = len(json.dumps(context)) // 4

        return {
            "answer": answer,
            "context_tokens": context_tokens,
            "question": question,
        }

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def _build_context(self) -> dict:
        ctx = Compressor(str(self.root)).compress()
        health = self._load_health()
        central = self._load_central_files()
        issues = self._build_issues_text(health)
        decisions = "\n".join(f"- {d}" for d in ctx.get("decisions", [])) or "_none recorded_"
        patterns = "\n".join(f"- {p}" for p in ctx.get("patterns", [])[:6]) or "_none detected_"
        conventions = "\n".join(f"- {c}" for c in ctx.get("coding_style", [])[:5]) or "_none detected_"

        return {
            "project_name":  self.root.name,
            "language":      ctx.get("language", "unknown"),
            "frameworks":    ctx.get("frameworks", "none"),
            "database":      ctx.get("database", "none"),
            "architecture":  ctx.get("architecture", "unknown"),
            "overall":       health.get("overall", "?"),
            "arch_score":    health.get("architecture", "?"),
            "sec_score":     health.get("security", "?"),
            "maint_score":   health.get("maintainability", "?"),
            "quality_score": health.get("code_quality", "?"),
            "critical_files": central,
            "issues":        issues,
            "decisions":     decisions,
            "patterns":      patterns,
            "conventions":   conventions,
        }

    def _load_health(self) -> dict:
        hp = self.pm_dir / "health_score.json"
        if hp.exists():
            try:
                return json.loads(hp.read_text())
            except Exception:
                pass
        return {}

    def _load_central_files(self, top_n: int = 8) -> str:
        graph_file = self.pm_dir / "knowledge_graph" / "graph.json"
        if not graph_file.exists():
            return "_Graph not built — run `projectmind graph build` first_"
        try:
            from backend.core.graph.queries import GraphQueries
            from backend.core.graph.serializer import GraphSerializer
            g = GraphSerializer().load(graph_file)
            q = GraphQueries(g, str(self.root))
            entries = q.most_central(top_n=top_n)
            lines = [
                f"{i}. `{e['file']}`  (score: {e['centrality_score']})"
                for i, e in enumerate(entries, 1)
            ]
            return "\n".join(lines) if lines else "_no data_"
        except Exception:
            return "_Graph load failed_"

    def _build_issues_text(self, health: dict) -> str:
        b = health.get("breakdown", {})
        if not b:
            return "_No analysis data — run `projectmind analyze` first_"
        sec_errors   = b.get("security_errors", 0)
        sec_warnings = b.get("security_warnings", 0)
        circ         = b.get("circular_dependencies", 0)
        dead_fn      = b.get("dead_functions", 0)
        dead_cl      = b.get("dead_classes", 0)
        dups         = b.get("duplicate_functions", 0)
        complex_fn   = b.get("high_complexity_functions", 0)

        lines = []
        if sec_errors:   lines.append(f"- **{sec_errors} security errors** (CRITICAL — fix before shipping)")
        if sec_warnings: lines.append(f"- {sec_warnings} security warnings")
        if circ:         lines.append(f"- {circ} circular dependency cycle(s)")
        if dead_fn + dead_cl: lines.append(f"- {dead_fn} dead functions, {dead_cl} dead classes (unused code)")
        if dups:         lines.append(f"- {dups} duplicate function(s)")
        if complex_fn:   lines.append(f"- {complex_fn} high-complexity function(s) (cyclomatic > 10)")
        return "\n".join(lines) if lines else "- No significant issues detected"
