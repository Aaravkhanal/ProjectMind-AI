"""
Architecture analysis route — runs the full Phase 2 static analysis pipeline.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.analyzer.ast_parser import ProjectParser
from backend.core.analyzer.dead_code import DeadCodeDetector
from backend.core.analyzer.dependency import DependencyAnalyzer
from backend.core.analyzer.duplicates import DuplicateDetector
from backend.core.analyzer.reporter import ArchitectureReport, Reporter
from backend.core.analyzer.security import SecurityScanner

router = APIRouter(prefix="/architecture", tags=["architecture"])


class ArchitectureAnalyzeRequest(BaseModel):
    project_path: str
    max_files: int = 500
    save_report: bool = True


class HealthSummary(BaseModel):
    overall: float
    architecture: float
    security: float
    maintainability: float
    code_quality: float
    breakdown: dict


class ArchitectureAnalyzeResponse(BaseModel):
    project_path: str
    language: str
    files_analyzed: int
    total_functions: int
    total_classes: int
    total_loc: int
    health: HealthSummary
    circular_dependencies_count: int
    duplicate_functions_count: int
    dead_code_count: int
    security_issues_count: int
    security_errors_count: int
    high_complexity_functions_count: int
    report_path: Optional[str]
    health_score_path: Optional[str]


@router.post("", response_model=ArchitectureAnalyzeResponse)
def analyze_architecture(req: ArchitectureAnalyzeRequest):
    root = Path(req.project_path).resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {root}")

    # 1. Parse all Python files
    parser = ProjectParser(str(root))
    analyses = parser.parse(max_files=req.max_files)

    if not analyses:
        raise HTTPException(
            status_code=422,
            detail="No Python source files found in the project.",
        )

    file_paths = [a.path for a in analyses if not a.parse_error]

    # 2. Dependency analysis
    dep_report = DependencyAnalyzer(str(root), analyses).analyze()

    # 3. Duplicate detection
    dup_report = DuplicateDetector(analyses).detect()

    # 4. Dead code detection
    dead_report = DeadCodeDetector(analyses).detect()

    # 5. Security scanning
    security_issues = SecurityScanner(str(root)).scan(file_paths)

    # 6. Build report
    reporter = Reporter(
        project_root=str(root),
        language="python",
        file_analyses=analyses,
        dep_report=dep_report,
        dup_report=dup_report,
        dead_report=dead_report,
        security_issues=security_issues,
    )
    report = reporter.build()

    report_path: Optional[str] = None
    health_score_path: Optional[str] = None
    if req.save_report:
        rp, hp = reporter.save(report)
        report_path = str(rp)
        health_score_path = str(hp)

    return ArchitectureAnalyzeResponse(
        project_path=str(root),
        language="python",
        files_analyzed=report.files_analyzed,
        total_functions=report.total_functions,
        total_classes=report.total_classes,
        total_loc=report.total_loc,
        health=HealthSummary(
            overall=report.health.overall,
            architecture=report.health.architecture,
            security=report.health.security,
            maintainability=report.health.maintainability,
            code_quality=report.health.code_quality,
            breakdown=report.health.breakdown,
        ),
        circular_dependencies_count=len(report.circular_dependencies),
        duplicate_functions_count=len(report.duplicate_groups),
        dead_code_count=len(report.dead_code),
        security_issues_count=len(report.security_issues),
        security_errors_count=report.health.breakdown.get("security_errors", 0),
        high_complexity_functions_count=len(report.high_complexity_functions),
        report_path=report_path,
        health_score_path=health_score_path,
    )


@router.get("/report")
def get_report(project_path: str):
    """Return the cached architecture_report.json if it exists."""
    report_file = Path(project_path) / ".projectmind" / "architecture_report.json"
    if not report_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No report found. Run POST /architecture first.",
        )
    return json.loads(report_file.read_text())


@router.get("/health")
def get_health(project_path: str):
    """Return the cached health_score.json if it exists."""
    health_file = Path(project_path) / ".projectmind" / "health_score.json"
    if not health_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No health score found. Run POST /architecture first.",
        )
    return json.loads(health_file.read_text())
