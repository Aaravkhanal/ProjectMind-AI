"""
Reporter — aggregates all Phase 2 analysis results into a health score
and writes architecture_report.json + health_score.json to .projectmind/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.core.analyzer.ast_parser import FileAnalysis, FunctionInfo
from backend.core.analyzer.dead_code import DeadCodeReport
from backend.core.analyzer.dependency import DependencyReport
from backend.core.analyzer.duplicates import DuplicateReport
from backend.core.analyzer.security import SecurityIssue, Severity


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

@dataclass
class HealthScore:
    overall: float
    architecture: float
    security: float
    maintainability: float
    code_quality: float
    breakdown: dict = field(default_factory=dict)

    def summary_line(self) -> str:
        return (
            f"Project Health: {self.overall:.1f}/10  "
            f"| Architecture: {self.architecture:.1f}  "
            f"| Security: {self.security:.1f}  "
            f"| Maintainability: {self.maintainability:.1f}  "
            f"| Code Quality: {self.code_quality:.1f}"
        )


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, value))


def calculate_health(
    dep: DependencyReport,
    dup: DuplicateReport,
    dead: DeadCodeReport,
    security: list[SecurityIssue],
    analyses: list[FileAnalysis],
) -> HealthScore:
    sec_errors = [i for i in security if i.severity == Severity.ERROR]
    sec_warnings = [i for i in security if i.severity == Severity.WARNING]
    high_complexity = [
        fn
        for a in analyses
        for fn in a.functions
        if fn.complexity > 10
    ]
    parse_errors = [a for a in analyses if a.parse_error]

    # ------------------------------------------------------------------
    # Architecture score (10 base)
    # ------------------------------------------------------------------
    arch = 10.0
    arch -= len(dep.circular_dependencies) * 1.5
    arch -= len(dep.unused_imports) * 0.05
    arch = _clamp(arch)

    # ------------------------------------------------------------------
    # Security score (10 base)
    # Cap deductions so warnings alone can't tank to 0.
    # Each error costs up to 1.5 pts (max -6 from errors).
    # Each warning costs 0.1 pts (max -2 from warnings).
    # ------------------------------------------------------------------
    sec = 10.0
    sec -= min(len(sec_errors) * 1.5, 6.0)
    sec -= min(len(sec_warnings) * 0.1, 2.0)
    sec = _clamp(sec)

    # ------------------------------------------------------------------
    # Maintainability score (10 base)
    # ------------------------------------------------------------------
    maint = 10.0
    maint -= dup.total_duplicate_functions * 0.3
    maint -= len(dead.dead_functions) * 0.1
    maint -= len(dead.dead_classes) * 0.15
    maint -= len(high_complexity) * 0.2
    maint -= len(parse_errors) * 0.5
    maint = _clamp(maint)

    # ------------------------------------------------------------------
    # Code quality (average of the above three)
    # ------------------------------------------------------------------
    quality = (arch + sec + maint) / 3.0

    # ------------------------------------------------------------------
    # Overall (weighted: arch 25%, sec 35%, maint 25%, quality 15%)
    # ------------------------------------------------------------------
    overall = arch * 0.25 + sec * 0.35 + maint * 0.25 + quality * 0.15
    overall = _clamp(overall)

    return HealthScore(
        overall=round(overall, 1),
        architecture=round(arch, 1),
        security=round(sec, 1),
        maintainability=round(maint, 1),
        code_quality=round(quality, 1),
        breakdown={
            "circular_dependencies": len(dep.circular_dependencies),
            "unused_imports": len(dep.unused_imports),
            "duplicate_functions": dup.total_duplicate_functions,
            "dead_functions": len(dead.dead_functions),
            "dead_classes": len(dead.dead_classes),
            "security_errors": len(sec_errors),
            "security_warnings": len(sec_warnings),
            "high_complexity_functions": len(high_complexity),
            "parse_errors": len(parse_errors),
        },
    )


# ---------------------------------------------------------------------------
# Full architecture report
# ---------------------------------------------------------------------------

@dataclass
class ArchitectureReport:
    project_path: str
    generated_at: str
    language: str
    files_analyzed: int
    total_functions: int
    total_classes: int
    total_loc: int
    health: HealthScore

    circular_dependencies: list[dict]
    unused_imports: list[dict]
    duplicate_groups: list[dict]
    dead_code: list[dict]
    security_issues: list[dict]
    high_complexity_functions: list[dict]
    most_imported_modules: list[dict]

    def print_summary(self):
        import click
        hs = self.health

        def _score_color(val: float) -> str:
            color = "green" if val >= 7.5 else "yellow" if val >= 5.0 else "red"
            return click.style(f"{val:.1f}", fg=color, bold=True)

        click.echo()
        click.echo(click.style(" Architecture Report", fg="bright_white", bold=True))
        click.echo(click.style(" " + "─" * 50, fg="bright_black"))
        click.echo(f"  Project      {click.style(Path(self.project_path).name, fg='cyan')}")
        click.echo(f"  Language     {self.language}")
        click.echo(f"  Files        {self.files_analyzed}  |  Functions: {self.total_functions}  |  Classes: {self.total_classes}")
        click.echo(f"  Lines        {self.total_loc:,}")
        click.echo()
        click.echo(click.style(" Health Scores", fg="bright_white", bold=True))
        click.echo(click.style(" " + "─" * 50, fg="bright_black"))
        click.echo(f"  Overall          {_score_color(hs.overall)} / 10")
        click.echo(f"  Architecture     {_score_color(hs.architecture)}")
        click.echo(f"  Security         {_score_color(hs.security)}")
        click.echo(f"  Maintainability  {_score_color(hs.maintainability)}")
        b = hs.breakdown
        click.echo()
        click.echo(click.style(" Issues", fg="bright_white", bold=True))
        click.echo(click.style(" " + "─" * 50, fg="bright_black"))

        def _row(label: str, count: int, bad_threshold: int = 1):
            color = "red" if count >= bad_threshold else "green"
            val = click.style(str(count), fg=color)
            click.echo(f"  {label:<22} {val}")

        _row("Circular deps",      b["circular_dependencies"])
        _row("Duplicate functions", b["duplicate_functions"])
        _row("Dead functions",      b["dead_functions"])
        _row("Dead classes",        b["dead_classes"])
        _row("Unused imports",      b["unused_imports"])
        _row("Security errors",     b["security_errors"])
        _row("Security warnings",   b["security_warnings"], bad_threshold=5)
        _row("High complexity",     b["high_complexity_functions"], bad_threshold=3)
        click.echo()


class Reporter:
    def __init__(
        self,
        project_root: str,
        language: str,
        file_analyses: list[FileAnalysis],
        dep_report: DependencyReport,
        dup_report: DuplicateReport,
        dead_report: DeadCodeReport,
        security_issues: list[SecurityIssue],
    ):
        self.root = Path(project_root)
        self.language = language
        self.analyses = file_analyses
        self.dep = dep_report
        self.dup = dup_report
        self.dead = dead_report
        self.security = security_issues

    def build(self) -> ArchitectureReport:
        health = calculate_health(
            self.dep, self.dup, self.dead, self.security, self.analyses
        )

        high_complexity: list[FunctionInfo] = sorted(
            [fn for a in self.analyses for fn in a.functions if fn.complexity > 10],
            key=lambda f: f.complexity,
            reverse=True,
        )

        return ArchitectureReport(
            project_path=str(self.root),
            generated_at=datetime.now(timezone.utc).isoformat(),
            language=self.language,
            files_analyzed=len(self.analyses),
            total_functions=sum(len(a.functions) for a in self.analyses),
            total_classes=sum(len(a.classes) for a in self.analyses),
            total_loc=sum(a.loc for a in self.analyses),
            health=health,
            circular_dependencies=[
                {"cycle": cd.cycle, "description": str(cd)}
                for cd in self.dep.circular_dependencies
            ],
            unused_imports=[
                {
                    "file": self._rel(ui.file),
                    "line": ui.line,
                    "module": ui.module,
                    "name": ui.name,
                }
                for ui in self.dep.unused_imports
            ],
            duplicate_groups=[
                {
                    "body_hash": g.body_hash,
                    "line_count": g.line_count,
                    "occurrences": len(g.functions),
                    "functions": [
                        {
                            "name": fn.qualified_name,
                            "file": self._rel(fn.file),
                            "line": fn.line_start,
                        }
                        for fn in g.functions
                    ],
                }
                for g in self.dup.groups
            ],
            dead_code=[
                {
                    "kind": d.kind,
                    "name": d.name,
                    "file": self._rel(d.file),
                    "line": d.line,
                    "confidence": d.confidence,
                    "reason": d.reason,
                }
                for d in (self.dead.dead_functions + self.dead.dead_classes)
            ],
            security_issues=[
                {
                    "severity": si.severity.value,
                    "rule_id": si.rule_id,
                    "file": self._rel(si.file),
                    "line": si.line,
                    "description": si.description,
                    "snippet": si.snippet,
                    "cwe": si.cwe,
                }
                for si in sorted(self.security, key=lambda x: x.severity.value)
            ],
            high_complexity_functions=[
                {
                    "name": fn.qualified_name,
                    "file": self._rel(fn.file),
                    "line": fn.line_start,
                    "complexity": fn.complexity,
                }
                for fn in high_complexity
            ],
            most_imported_modules=[
                {"module": m, "import_count": c}
                for m, c in self.dep.most_imported
            ],
        )

    def save(self, report: ArchitectureReport) -> tuple[Path, Path]:
        pm_dir = self.root / ".projectmind"
        pm_dir.mkdir(exist_ok=True)

        report_dict = self._report_to_dict(report)

        report_path = pm_dir / "architecture_report.json"
        report_path.write_text(json.dumps(report_dict, indent=2))

        health_dict = {
            "overall": report.health.overall,
            "architecture": report.health.architecture,
            "security": report.health.security,
            "maintainability": report.health.maintainability,
            "code_quality": report.health.code_quality,
            "breakdown": report.health.breakdown,
            "generated_at": report.generated_at,
        }
        health_path = pm_dir / "health_score.json"
        health_path.write_text(json.dumps(health_dict, indent=2))

        # Auto-save snapshot for `projectmind diff`
        try:
            from backend.core.diff.snapshots import save_snapshot
            save_snapshot(pm_dir, health_dict, self.root)
        except Exception:
            pass

        return report_path, health_path

    def _rel(self, filepath: str) -> str:
        try:
            return str(Path(filepath).relative_to(self.root))
        except ValueError:
            return filepath

    @staticmethod
    def _report_to_dict(report: ArchitectureReport) -> dict:
        d = {
            "project_path": report.project_path,
            "generated_at": report.generated_at,
            "language": report.language,
            "files_analyzed": report.files_analyzed,
            "total_functions": report.total_functions,
            "total_classes": report.total_classes,
            "total_loc": report.total_loc,
            "health": {
                "overall": report.health.overall,
                "architecture": report.health.architecture,
                "security": report.health.security,
                "maintainability": report.health.maintainability,
                "code_quality": report.health.code_quality,
                "breakdown": report.health.breakdown,
            },
            "circular_dependencies": report.circular_dependencies,
            "unused_imports": report.unused_imports,
            "duplicate_groups": report.duplicate_groups,
            "dead_code": report.dead_code,
            "security_issues": report.security_issues,
            "high_complexity_functions": report.high_complexity_functions,
            "most_imported_modules": report.most_imported_modules,
        }
        return d
