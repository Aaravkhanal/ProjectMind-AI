"""
CommitClassifier — labels commits by type using pure heuristics (no LLM).

Types:
  feature    — new capability added
  bug_fix    — defect corrected
  refactor   — code restructured, no behaviour change
  test       — tests added or updated
  docs       — documentation only
  chore      — build, CI, deps, tooling
  revert     — reverts a previous commit
  other      — anything that doesn't match the above

Classification uses Conventional Commits prefixes first,
then falls back to keyword scanning of the full message.
"""

from __future__ import annotations

import re

# Conventional Commits prefix → type
_CC_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^feat(?:\(.+\))?!?:', re.I),     "feature"),
    (re.compile(r'^fix(?:\(.+\))?!?:', re.I),      "bug_fix"),
    (re.compile(r'^refactor(?:\(.+\))?!?:', re.I), "refactor"),
    (re.compile(r'^test(?:s)?(?:\(.+\))?!?:', re.I), "test"),
    (re.compile(r'^docs?(?:\(.+\))?!?:', re.I),    "docs"),
    (re.compile(r'^chore(?:\(.+\))?!?:', re.I),    "chore"),
    (re.compile(r'^ci(?:\(.+\))?!?:', re.I),       "chore"),
    (re.compile(r'^build(?:\(.+\))?!?:', re.I),    "chore"),
    (re.compile(r'^perf(?:\(.+\))?!?:', re.I),     "refactor"),
    (re.compile(r'^style(?:\(.+\))?!?:', re.I),    "chore"),
    (re.compile(r'^revert(?:\(.+\))?!?:', re.I),   "revert"),
]

# Keyword fallback — matched against lowercased full message
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["revert", "undo", "rollback"],              "revert"),
    (["fix", "bug", "hotfix", "patch", "repair",
      "resolve", "regression", "broke", "broken",
      "incorrect", "wrong", "typo in logic"],     "bug_fix"),
    (["test", "spec", "coverage", "unittest",
      "pytest", "jest", "mock"],                  "test"),
    (["refactor", "clean", "cleanup", "extract",
      "rename", "reorganise", "reorganize",
      "restructure", "simplify", "dedup"],        "refactor"),
    (["doc", "readme", "changelog", "comment",
      "docstring", "document", "wiki"],           "docs"),
    (["ci", "cd", "pipeline", "workflow",
      "docker", "makefile", "dependency",
      "upgrade", "bump", "chore", "lint",
      "format", "prettier", "eslint"],            "chore"),
    (["add", "feat", "feature", "new", "create",
      "implement", "introduce", "support",
      "enable", "allow", "expose"],               "feature"),
]


def classify(message: str) -> str:
    """
    Classify a commit message into one of the commit types.
    Returns the type string.
    """
    msg = message.strip()
    if not msg:
        return "other"

    # 1. Merge commit
    if re.match(r'^merge\b', msg, re.I):
        return "other"

    # 2. Conventional Commits prefix (fast path)
    for pattern, commit_type in _CC_MAP:
        if pattern.match(msg):
            return commit_type

    # 3. Keyword fallback on lowercased message
    lower = msg.lower()
    for keywords, commit_type in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            return commit_type

    return "other"


def classify_batch(messages: list[str]) -> list[str]:
    return [classify(m) for m in messages]


def type_distribution(messages: list[str]) -> dict[str, int]:
    """Returns a count of each commit type across a list of messages."""
    dist: dict[str, int] = {}
    for t in classify_batch(messages):
        dist[t] = dist.get(t, 0) + 1
    return dist
