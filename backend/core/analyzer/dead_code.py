"""
Dead Code Detector — identifies functions and classes defined in the project
but never referenced anywhere outside their own file.

Conservative approach: a definition is only flagged as dead if it is:
  - not referenced by name anywhere in the project outside its defining file
  - not a dunder method (__init__, __str__, etc.)
  - not decorated with a framework registration decorator
  - not a test function (test_*) or fixture
  - not marked as an entry point (main, cli, app, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.analyzer.ast_parser import FileAnalysis, FunctionInfo, ClassInfo


# Decorators that register a function with a framework — not dead even if uncalled
_REGISTRATION_DECORATORS = {
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "app.route", "blueprint.route",
    "task", "shared_task", "periodic_task",
    "property", "staticmethod", "classmethod",
    "abstractmethod",
    "pytest.fixture", "fixture",
    "click.command", "command", "cli.command", "group.command",
    "lru_cache", "cache", "cached_property",
    "override",
}

_ENTRY_POINT_NAMES = {
    "main", "run", "start", "serve", "cli", "app", "create_app", "get_app",
    "setup", "teardown", "conftest",
}


@dataclass
class DeadItem:
    kind: str          # "function" | "class"
    name: str
    file: str
    line: int
    confidence: str    # "high" | "medium"
    reason: str


@dataclass
class DeadCodeReport:
    dead_functions: list[DeadItem]
    dead_classes: list[DeadItem]

    @property
    def total(self) -> int:
        return len(self.dead_functions) + len(self.dead_classes)


class DeadCodeDetector:
    def __init__(self, file_analyses: list[FileAnalysis]):
        self.analyses = file_analyses

    def detect(self) -> DeadCodeReport:
        # Build a global set of all names used anywhere in the project
        global_used: set[str] = set()
        for a in self.analyses:
            global_used |= a.used_names

        dead_fns: list[DeadItem] = []
        dead_cls: list[DeadItem] = []

        for analysis in self.analyses:
            for fn in analysis.functions:
                item = self._check_function(fn, analysis.path, global_used)
                if item:
                    dead_fns.append(item)

            for cl in analysis.classes:
                item = self._check_class(cl, analysis.path, global_used)
                if item:
                    dead_cls.append(item)

        return DeadCodeReport(dead_functions=dead_fns, dead_classes=dead_cls)

    # ------------------------------------------------------------------

    def _check_function(
        self,
        fn: FunctionInfo,
        filepath: str,
        global_used: set[str],
    ) -> DeadItem | None:
        name = fn.name

        # Never flag dunder methods
        if name.startswith("__") and name.endswith("__"):
            return None

        # Never flag test functions / fixtures
        if name.startswith("test_") or name.startswith("fixture_"):
            return None

        # Never flag AST/framework visitor/handler callbacks (called by dispatch)
        if name.startswith("visit_") or name.startswith("on_") or name.startswith("handle_"):
            return None

        # Never flag known entry-point names
        if name in _ENTRY_POINT_NAMES:
            return None

        # Never flag private helpers (could be used dynamically)
        if name.startswith("_"):
            return None

        # Never flag if decorated with a framework registration decorator
        for dec in fn.decorators:
            dec_clean = dec.split("(")[0].strip()
            if dec_clean in _REGISTRATION_DECORATORS or any(
                dec_clean.endswith("." + r) for r in _REGISTRATION_DECORATORS
            ):
                return None

        # If name appears anywhere in the project at all, not dead
        if name in global_used:
            return None

        return DeadItem(
            kind="function",
            name=fn.qualified_name,
            file=filepath,
            line=fn.line_start,
            confidence="high" if not fn.is_method else "medium",
            reason=f"Never referenced anywhere in the project",
        )

    def _check_class(
        self,
        cl: ClassInfo,
        filepath: str,
        global_used: set[str],
    ) -> DeadItem | None:
        name = cl.name

        if name.startswith("_"):
            return None

        if name in global_used:
            return None

        return DeadItem(
            kind="class",
            name=name,
            file=filepath,
            line=cl.line_start,
            confidence="medium",
            reason="Class never instantiated or referenced anywhere in the project",
        )
