"""
PlanParser — converts PlannerAgent markdown output into structured PlanStep dicts.

The planner reliably outputs this structure:
  ## Goal
  <one sentence>

  ## Steps
  1. **<title>** — <files> (Effort: <XS|S|M|L|XL>)
     <description lines>

  2. **<title>** ...

  ## Risks & Dependencies
  ...

  ## Definition of Done
  ...

Parsing is purely regex — no LLM call, instant.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class ParsedStep:
    number: int
    title: str
    description: str
    files: list[str]
    effort: str
    agent_type: str | None   # inferred from title/description keywords


@dataclass
class ParsedPlan:
    goal: str
    steps: list[ParsedStep]
    risks: str
    definition_of_done: str
    raw: str


# ── helpers ────────────────────────────────────────────────────────────────────

_EFFORT_RE    = re.compile(r'\b(effort|size)[:\s]+([XSMLxsml]{1,2})\b', re.I)
_EFFORT_ABBR  = re.compile(r'\b([XS]S|[SML]|XL)\b')
_FILES_RE     = re.compile(r'(?:files?|touch)[:\s]+([^\n]{3,120})', re.I)
_BOLD_TITLE   = re.compile(r'^\*{1,2}(.+?)\*{1,2}')

_AGENT_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\btest\b|\bspec\b|\bcoverage\b',    re.I), "testing"),
    (re.compile(r'\bdocument\b|\bdocstring\b|\breadme\b', re.I), "docs"),
    (re.compile(r'\brefactor\b|\bclean\b|\bextract\b', re.I), "refactor"),
]


def _infer_agent(text: str) -> str | None:
    for pattern, agent in _AGENT_HINTS:
        if pattern.search(text):
            return agent
    return None


def _extract_files(text: str) -> list[str]:
    """Pull file paths from a step's description text."""
    files: list[str] = []
    m = _FILES_RE.search(text)
    if m:
        raw = m.group(1)
        # Split on comma, semicolon, or 'and'
        parts = re.split(r'[,;]|\band\b', raw)
        for p in parts:
            p = p.strip().strip('"').strip("'")
            # Keep if it looks like a path
            if "/" in p or p.endswith(".py") or p.endswith(".ts") or p.endswith(".md"):
                files.append(p)
    # Also look for bare paths anywhere in the text
    bare = re.findall(r'\b[\w/.-]+\.(?:py|ts|tsx|js|go|rs|java|md|yaml|yml|json)\b', text)
    files.extend(bare)
    return list(dict.fromkeys(files))[:6]   # deduplicate, cap at 6


def _extract_effort(text: str) -> str:
    m = _EFFORT_RE.search(text)
    if m:
        return m.group(2).upper()
    m = _EFFORT_ABBR.search(text)
    if m:
        val = m.group(1).upper()
        if val in ("XS", "S", "M", "L", "XL"):
            return val
    return "M"


def _section(text: str, header: str) -> str:
    """Extract the content of a markdown ## header section."""
    pattern = re.compile(
        rf'^##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def parse(planner_output: str) -> ParsedPlan:
    """Parse PlannerAgent markdown output into a ParsedPlan."""
    raw = planner_output.strip()

    goal = _section(raw, "Goal").split("\n")[0].strip()
    if not goal:
        # Fallback: first non-empty line
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                goal = line
                break
    goal = goal or "Implement the planned changes."

    risks = _section(raw, "Risks.*") or _section(raw, "Risks & Dependencies") or ""
    dod   = _section(raw, "Definition of Done") or ""

    # ── Parse steps ─────────────────────────────────────────────────────────
    steps_text = _section(raw, "Steps")
    steps: list[ParsedStep] = []

    # Each step starts with a number: "1." or "1)"
    step_blocks = re.split(r'\n(?=\d+[.)]\s)', "\n" + steps_text)
    for block in step_blocks:
        block = block.strip()
        if not block:
            continue
        # First line: "1. **Title** — files (Effort: M)"
        first_line, *rest_lines = block.splitlines()
        # Remove leading number
        first_line = re.sub(r'^\d+[.)]\s*', '', first_line).strip()

        # Extract title (bold or plain)
        m = _BOLD_TITLE.match(first_line)
        title = m.group(1).strip() if m else first_line.split("—")[0].strip()
        title = re.sub(r'\s+', ' ', title).strip("* ")

        if not title:
            continue

        body = "\n".join(rest_lines)
        full_text = first_line + "\n" + body

        effort = _extract_effort(full_text)
        files  = _extract_files(full_text)
        agent  = _infer_agent(title + " " + body)
        desc   = "\n".join(
            l.strip().lstrip("-•* ") for l in rest_lines if l.strip()
        ).strip()

        steps.append(ParsedStep(
            number=len(steps) + 1,
            title=title[:200],
            description=desc[:1000],
            files=files,
            effort=effort,
            agent_type=agent,
        ))

    # Fallback: if no structured steps found, create one generic step
    if not steps:
        steps.append(ParsedStep(
            number=1,
            title="Implement the plan",
            description=raw[:500],
            files=[],
            effort="M",
            agent_type=None,
        ))

    return ParsedPlan(
        goal=goal,
        steps=steps,
        risks=risks,
        definition_of_done=dod,
        raw=raw,
    )
