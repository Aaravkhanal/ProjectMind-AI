"""
Duplicate Detector — identifies copy-pasted or structurally identical functions
across the project using AST body hashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from backend.core.analyzer.ast_parser import FileAnalysis, FunctionInfo


@dataclass
class DuplicateGroup:
    body_hash: str
    functions: list[FunctionInfo]
    line_count: int

    @property
    def representative(self) -> FunctionInfo:
        return self.functions[0]


@dataclass
class DuplicateReport:
    groups: list[DuplicateGroup]
    total_duplicate_functions: int
    wasted_lines: int


# Functions shorter than this are not worth flagging (trivial getters, etc.)
MIN_BODY_LINES = 3


class DuplicateDetector:
    def __init__(self, file_analyses: list[FileAnalysis]):
        self.analyses = file_analyses

    def detect(self) -> DuplicateReport:
        by_hash: dict[str, list[FunctionInfo]] = defaultdict(list)

        for analysis in self.analyses:
            for fn in analysis.functions:
                if not fn.body_hash:
                    continue
                body_lines = fn.line_end - fn.line_start
                if body_lines < MIN_BODY_LINES:
                    continue
                # Skip dunder methods — they are commonly similar by convention
                if fn.name.startswith("__") and fn.name.endswith("__"):
                    continue
                by_hash[fn.body_hash].append(fn)

        groups: list[DuplicateGroup] = []
        total_duplicate = 0
        wasted = 0

        for body_hash, fns in by_hash.items():
            if len(fns) < 2:
                continue
            line_count = fns[0].line_end - fns[0].line_start
            groups.append(DuplicateGroup(
                body_hash=body_hash,
                functions=fns,
                line_count=line_count,
            ))
            # All but the original are duplicates
            total_duplicate += len(fns) - 1
            wasted += line_count * (len(fns) - 1)

        # Sort by most occurrences first
        groups.sort(key=lambda g: len(g.functions), reverse=True)

        return DuplicateReport(
            groups=groups,
            total_duplicate_functions=total_duplicate,
            wasted_lines=wasted,
        )
