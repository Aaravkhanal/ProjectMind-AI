"""
AST Parser — extracts structural metadata from Python source files.
Uses the built-in `ast` module; zero external dependencies.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.core.analyzer.cache import AnalysisCache


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FunctionInfo:
    name: str
    file: str
    line_start: int
    line_end: int
    params: list[str]
    body_hash: str
    complexity: int
    decorators: list[str]
    is_async: bool = False
    is_method: bool = False
    parent_class: Optional[str] = None
    docstring: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name


@dataclass
class ClassInfo:
    name: str
    file: str
    line_start: int
    line_end: int
    methods: list[str]
    base_classes: list[str]
    docstring: Optional[str] = None


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    file: str
    line: int
    is_from: bool = False
    alias: Optional[str] = None


@dataclass
class FileAnalysis:
    path: str
    language: str
    loc: int
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    defined_names: set[str] = field(default_factory=set)
    used_names: set[str] = field(default_factory=set)
    parse_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Cyclomatic complexity visitor
# ---------------------------------------------------------------------------

class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node: ast.If):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension):
        self.complexity += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert):
        self.complexity += 1
        self.generic_visit(node)

    def visit_Match(self, node):
        # Python 3.10+ match/case
        self.complexity += len(getattr(node, "cases", []))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Name usage collector
# ---------------------------------------------------------------------------

class _NameCollector(ast.NodeVisitor):
    def __init__(self):
        self.used: set[str] = set()

    def visit_Name(self, node: ast.Name):
        self.used.add(node.id)

    def visit_Attribute(self, node: ast.Attribute):
        self.used.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.used.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.used.add(node.func.attr)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Function body hasher
# ---------------------------------------------------------------------------

def _hash_body(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        body_src = "\n".join(ast.unparse(stmt) for stmt in func_node.body)
        return hashlib.md5(body_src.encode()).hexdigest()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Python file parser
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 512 * 1024  # skip files larger than 512 KB


class PythonASTParser:
    def parse_file(self, filepath: Path) -> FileAnalysis:
        analysis = FileAnalysis(path=str(filepath), language="python", loc=0)

        if filepath.stat().st_size > MAX_FILE_BYTES:
            analysis.parse_error = "file too large"
            return analysis

        source = filepath.read_text(encoding="utf-8", errors="replace")
        analysis.loc = source.count("\n") + 1

        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError as e:
            analysis.parse_error = str(e)
            return analysis

        analysis.imports = self._extract_imports(tree, str(filepath))
        analysis.functions, analysis.classes = self._extract_definitions(
            tree, str(filepath)
        )

        # Collect all defined names
        for fn in analysis.functions:
            analysis.defined_names.add(fn.name)
        for cl in analysis.classes:
            analysis.defined_names.add(cl.name)

        # Collect all used names
        collector = _NameCollector()
        collector.visit(tree)
        analysis.used_names = collector.used

        return analysis

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _extract_imports(self, tree: ast.AST, filepath: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ImportInfo(
                        module=alias.name,
                        names=[],
                        file=filepath,
                        line=node.lineno,
                        is_from=False,
                        alias=alias.asname,
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Prefix relative imports with dots to mark them
                if node.level:
                    module = "." * node.level + module
                names = [alias.name for alias in node.names]
                imports.append(ImportInfo(
                    module=module,
                    names=names,
                    file=filepath,
                    line=node.lineno,
                    is_from=True,
                ))
        return imports

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def _extract_definitions(
        self, tree: ast.AST, filepath: str
    ) -> tuple[list[FunctionInfo], list[ClassInfo]]:
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name
                    for n in ast.walk(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n is not node
                ]
                bases = []
                for base in node.bases:
                    try:
                        bases.append(ast.unparse(base))
                    except Exception:
                        pass
                classes.append(ClassInfo(
                    name=node.name,
                    file=filepath,
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    methods=methods,
                    base_classes=bases,
                    docstring=ast.get_docstring(node),
                ))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Determine if it's a method (parent is a class)
                parent_class = self._find_parent_class(tree, node)
                params = [arg.arg for arg in node.args.args]
                if parent_class:
                    params = params[1:]  # strip self/cls

                decorators = []
                for dec in node.decorator_list:
                    try:
                        decorators.append(ast.unparse(dec))
                    except Exception:
                        pass

                cv = _ComplexityVisitor()
                cv.visit(node)

                functions.append(FunctionInfo(
                    name=node.name,
                    file=filepath,
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    params=params,
                    body_hash=_hash_body(node),
                    complexity=cv.complexity,
                    decorators=decorators,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    is_method=parent_class is not None,
                    parent_class=parent_class,
                    docstring=ast.get_docstring(node),
                ))

        return functions, classes

    def _find_parent_class(
        self, tree: ast.AST, target: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Optional[str]:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if child is target:
                        return node.name
        return None


# ---------------------------------------------------------------------------
# Project-wide parser
# ---------------------------------------------------------------------------

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".pytest_cache", "htmlcov", ".tox",
    "migrations", ".projectmind",
}


class ProjectParser:
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self._python_parser = PythonASTParser()

    def parse(
        self,
        max_files: int = 500,
        cache: AnalysisCache | None = None,
    ) -> list[FileAnalysis]:
        py_files = [
            p for p in self.root.rglob("*.py")
            if not any(part in IGNORE_DIRS for part in p.parts)
        ][:max_files]

        if cache is None:
            return [self._python_parser.parse_file(fp) for fp in py_files]

        results: list[FileAnalysis] = []
        live = {str(fp) for fp in py_files}
        cache.evict_missing(live)

        for filepath in py_files:
            mtime = filepath.stat().st_mtime
            cached = cache.get(str(filepath), mtime)
            if cached is not None:
                results.append(cached)
            else:
                analysis = self._python_parser.parse_file(filepath)
                cache.put(str(filepath), mtime, analysis)
                results.append(analysis)

        cache.save()
        return results
