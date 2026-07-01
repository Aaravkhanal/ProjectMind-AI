"""
Security Scanner — regex + AST pattern-based scanning.
No external tools required; semgrep can layer on top later.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class SecurityIssue:
    severity: Severity
    rule_id: str
    file: str
    line: int
    description: str
    snippet: str
    cwe: str = ""


# ---------------------------------------------------------------------------
# Regex rules (applied line-by-line)
# ---------------------------------------------------------------------------

_REGEX_RULES: list[tuple[str, Severity, str, str, str]] = [
    # (pattern, severity, rule_id, description, cwe)

    # Code execution
    (r"(?<!\.)eval\s*\(", Severity.ERROR, "S001", "eval() allows arbitrary code execution", "CWE-95"),
    # Negative lookbehind so `.exec(` (SQLModel, asyncio) is not flagged
    (r"(?<![.\w])exec\s*\(", Severity.ERROR, "S002", "exec() allows arbitrary code execution", "CWE-95"),
    (r"\bcompile\s*\(.*eval", Severity.ERROR, "S003", "compile() with eval mode", "CWE-95"),

    # Deserialization
    (r"\bpickle\.loads?\s*\(", Severity.ERROR, "S004", "pickle.load() is unsafe with untrusted data (RCE risk)", "CWE-502"),
    (r"\byaml\.load\s*\([^,)]*\)", Severity.WARNING, "S005", "yaml.load() without explicit Loader is unsafe; use yaml.safe_load()", "CWE-20"),
    (r"\bjsonpickle\.decode\s*\(", Severity.ERROR, "S006", "jsonpickle.decode() can execute arbitrary code", "CWE-502"),

    # Shell injection
    (r"subprocess\.(call|run|Popen|check_output)\s*\([^)]*shell\s*=\s*True", Severity.ERROR, "S007", "subprocess with shell=True is vulnerable to shell injection", "CWE-78"),
    (r"\bos\.system\s*\(", Severity.ERROR, "S008", "os.system() passes commands to the shell; use subprocess instead", "CWE-78"),
    (r"\bos\.popen\s*\(", Severity.WARNING, "S009", "os.popen() is deprecated and vulnerable to injection", "CWE-78"),

    # SQL injection — pattern must be anchored to the execute call, not the whole file
    (r'(execute|executemany)\s*\(\s*f["\']', Severity.ERROR, "S011", "SQL query built with f-string — SQL injection risk", "CWE-89"),
    (r'(execute|executemany)\s*\(\s*["\'][^"\']*%[sd]', Severity.WARNING, "S010", "Possible SQL injection: use parameterised queries instead of %-formatting", "CWE-89"),
    (r'(execute|executemany)\s*\(\s*["\'][^"\']*\+', Severity.WARNING, "S010b", "Possible SQL injection: query built by string concatenation", "CWE-89"),

    # Hardcoded credentials
    (r'(?i)(password|passwd|secret|api_key|apikey|token|auth_token)\s*=\s*["\'][^"\']{6,}["\']', Severity.ERROR, "S012", "Possible hardcoded credential detected", "CWE-798"),
    (r'(?i)(AWS_SECRET|GITHUB_TOKEN|SLACK_TOKEN|STRIPE_KEY)\s*=\s*["\'][^"\']+["\']', Severity.ERROR, "S013", "Possible hardcoded cloud/service credential", "CWE-798"),

    # Weak cryptography
    (r"\bMD5\b|\bhashlib\.md5\s*\(", Severity.WARNING, "S014", "MD5 is cryptographically broken; use SHA-256 or better", "CWE-327"),
    (r"\bSHA1\b|\bhashlib\.sha1\s*\(", Severity.WARNING, "S015", "SHA-1 is cryptographically weak; use SHA-256 or better", "CWE-327"),
    (r"\brandom\.random\(\)|\brandom\.randint\(|\brandom\.choice\(", Severity.WARNING, "S016", "random module is not cryptographically secure; use secrets module instead", "CWE-338"),

    # Path traversal
    (r'open\s*\(\s*.*\+.*["\']', Severity.WARNING, "S017", "Possible path traversal: file path built by string concatenation", "CWE-22"),

    # Debug / info leaks
    (r"\bDEBUG\s*=\s*True", Severity.WARNING, "S018", "DEBUG=True should not be in production code", "CWE-215"),
    (r'\bprint\s*\(.*(?:password|token|secret|key)\b', Severity.WARNING, "S019", "Possible credential logged via print()", "CWE-312"),

    # Temp file
    (r"\btempfile\.mktemp\s*\(", Severity.WARNING, "S020", "tempfile.mktemp() is deprecated; use tempfile.mkstemp() to avoid race conditions", "CWE-377"),

    # XML
    (r"\bxml\.etree\.ElementTree\.parse\b|\bxml\.sax\b|\bxml\.dom\.minidom\b", Severity.INFO, "S021", "Standard XML parsers are vulnerable to XXE; consider using defusedxml", "CWE-611"),

    # Request timeout
    (r'requests\.(get|post|put|delete|patch)\s*\([^)]*\)', Severity.INFO, "S022", "HTTP request without explicit timeout may hang indefinitely", "CWE-400"),

    # assert removed in optimised mode
    (r'^\s*assert\s+', Severity.INFO, "S023", "assert statements are removed with python -O; do not use for input validation", "CWE-617"),
]

# Compile all patterns once
_COMPILED_RULES = [
    (re.compile(pattern), severity, rule_id, desc, cwe)
    for pattern, severity, rule_id, desc, cwe in _REGEX_RULES
]


# ---------------------------------------------------------------------------
# AST-based rules (more precise than regex)
# ---------------------------------------------------------------------------

class _ASTSecurityVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str, source_lines: list[str]):
        self.filepath = filepath
        self.source_lines = source_lines
        self.issues: list[SecurityIssue] = []

    def _snippet(self, line: int) -> str:
        idx = line - 1
        if 0 <= idx < len(self.source_lines):
            return self.source_lines[idx].strip()
        return ""

    def visit_Call(self, node: ast.Call):
        # Detect bare `except: pass` — caught in ExceptHandler
        # Detect assert with security implications
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Bare except: (no exception type)
        if node.type is None:
            body_trivial = all(isinstance(s, (ast.Pass, ast.Ellipsis)) for s in node.body)
            if body_trivial:
                self.issues.append(SecurityIssue(
                    severity=Severity.WARNING,
                    rule_id="S030",
                    file=self.filepath,
                    line=node.lineno,
                    description="Bare `except: pass` silently swallows all exceptions including KeyboardInterrupt and SystemExit",
                    snippet=self._snippet(node.lineno),
                    cwe="CWE-390",
                ))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        # Flag functions with no type annotations (info level)
        unannotated = [
            arg.arg for arg in node.args.args
            if arg.annotation is None and arg.arg not in ("self", "cls")
        ]
        if unannotated and len(node.args.args) > 1:
            # Only flag if it looks like a public API (no leading underscore)
            if not node.name.startswith("_"):
                self.issues.append(SecurityIssue(
                    severity=Severity.INFO,
                    rule_id="S031",
                    file=self.filepath,
                    line=node.lineno,
                    description=f"Function `{node.name}` has unannotated parameters: {unannotated}. Missing type hints reduce safety.",
                    snippet=self._snippet(node.lineno),
                ))
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

class SecurityScanner:
    def __init__(self, project_root: str):
        self.root = Path(project_root)

    def scan(self, file_paths: list[str]) -> list[SecurityIssue]:
        issues: list[SecurityIssue] = []
        for filepath in file_paths:
            issues.extend(self._scan_file(Path(filepath)))
        return issues

    def _scan_file(self, filepath: Path) -> list[SecurityIssue]:
        issues: list[SecurityIssue] = []

        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return issues

        lines = source.splitlines()

        # Regex-based scan (line by line)
        for lineno, line in enumerate(lines, start=1):
            # Skip comments and docstrings (rough heuristic)
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, severity, rule_id, desc, cwe in _COMPILED_RULES:
                if pattern.search(line):
                    # Avoid duplicate findings on the same line from similar rules
                    if not any(i.file == str(filepath) and i.line == lineno and i.rule_id == rule_id for i in issues):
                        issues.append(SecurityIssue(
                            severity=severity,
                            rule_id=rule_id,
                            file=str(filepath),
                            line=lineno,
                            description=desc,
                            snippet=stripped[:120],
                            cwe=cwe,
                        ))

        # AST-based scan
        try:
            tree = ast.parse(source, filename=str(filepath))
            visitor = _ASTSecurityVisitor(str(filepath), lines)
            visitor.visit(tree)
            issues.extend(visitor.issues)
        except SyntaxError:
            pass

        return issues
