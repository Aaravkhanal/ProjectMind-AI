"""
PRRiskScorer — scores the risk of a PR/diff on a 0–10 scale.

Six independent risk factors, each 0–10, combined into an overall score.

Factors:
  size_risk           — large diffs are harder to review and more likely to hide bugs
  churn_risk          — files that changed frequently recently are fragile
  critical_file_risk  — auth/payment/security/DB files carry inherent risk
  test_coverage_risk  — source changed without accompanying test changes
  author_risk         — author has historically introduced blocking issues
  complexity_risk     — diff contains signals of complex changes (schema, async, locks)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.core.git_intel.analyzer import ChurnData, parse_diff_files


# ── Critical file patterns ─────────────────────────────────────────────────────

_CRITICAL_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r'auth|login|password|token|jwt|oauth|session|credential', re.I), 9.0),
    (re.compile(r'payment|billing|invoice|stripe|checkout|subscription',   re.I), 9.5),
    (re.compile(r'migration|schema|alembic|flyway|liquibase',              re.I), 8.0),
    (re.compile(r'security|crypto|encrypt|decrypt|hash|salt',              re.I), 8.5),
    (re.compile(r'permission|acl|rbac|role|admin',                         re.I), 7.5),
    (re.compile(r'config|settings|env|secret|\.env',                       re.I), 6.5),
    (re.compile(r'middleware|interceptor|hook',                             re.I), 6.0),
]

# Diff keywords that signal higher complexity
_COMPLEXITY_SIGNALS: list[re.Pattern] = [
    re.compile(r'\basync\s+def\b|\bawait\b',      re.I),
    re.compile(r'\bthread\b|\bprocess\b|\block\b', re.I),
    re.compile(r'ALTER\s+TABLE|DROP\s+TABLE|CREATE\s+TABLE', re.I),
    re.compile(r'\brecursion\b|\brecursive\b',    re.I),
    re.compile(r'eval\(|exec\(',                  re.I),
    re.compile(r'sql\s*=\s*f"',                  re.I),
]

_TEST_PATTERNS = re.compile(r'^tests?/|test_|_test\.|\.spec\.|\.test\.', re.I)


# ── Risk data ──────────────────────────────────────────────────────────────────

@dataclass
class RiskBreakdown:
    factor: str
    score: float             # 0–10
    weight: float            # contribution weight
    explanation: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class RiskResult:
    overall_risk: float      # 0–10
    risk_level: str          # low|medium|high|critical
    diff_hash: str
    files_changed: list[str]
    critical_files: list[str]
    missing_tests: bool
    breakdown: list[RiskBreakdown]

    @property
    def summary(self) -> str:
        top = sorted(self.breakdown, key=lambda x: x.score * x.weight, reverse=True)
        lines = [f"**Risk: {self.risk_level.upper()}** ({self.overall_risk:.1f}/10)"]
        for b in top[:3]:
            if b.score > 2:
                lines.append(f"- {b.factor}: {b.explanation}")
        return "\n".join(lines)


# ── Scorer ─────────────────────────────────────────────────────────────────────

class PRRiskScorer:
    """
    Weights for combining factor scores into the overall risk score.
    Higher weight = more influence on the final number.
    """
    _WEIGHTS = {
        "size":          0.20,
        "churn":         0.25,
        "critical_file": 0.25,
        "test_coverage": 0.15,
        "author":        0.10,
        "complexity":    0.05,
    }

    def score(
        self,
        diff: str,
        project_path: str = ".",
        author: Optional[str] = None,
        pr_title: str = "",
        churn_data: Optional[dict[str, ChurnData]] = None,
        author_quality_score: Optional[float] = None,   # from brain DB (0–10, higher = better)
    ) -> RiskResult:
        files = parse_diff_files(diff)
        diff_hash = hashlib.md5(diff.encode()).hexdigest()[:16]

        breakdown = [
            self._size_risk(diff, files),
            self._churn_risk(files, churn_data or {}),
            self._critical_file_risk(files, pr_title),
            self._test_coverage_risk(diff, files),
            self._author_risk(author, author_quality_score),
            self._complexity_risk(diff),
        ]

        overall = sum(b.score * b.weight for b in breakdown)
        overall = round(min(10.0, overall / sum(b.weight for b in breakdown) * 10), 2)

        level = (
            "critical" if overall >= 8.0 else
            "high"     if overall >= 6.0 else
            "medium"   if overall >= 3.5 else
            "low"
        )

        critical_files = [
            f for f in files
            if any(p.search(f) for p, _ in _CRITICAL_PATTERNS)
        ]

        source_changed = [f for f in files if not _TEST_PATTERNS.search(f)]
        test_changed   = [f for f in files if _TEST_PATTERNS.search(f)]
        missing_tests  = bool(source_changed) and not bool(test_changed)

        return RiskResult(
            overall_risk=overall,
            risk_level=level,
            diff_hash=diff_hash,
            files_changed=files,
            critical_files=critical_files,
            missing_tests=missing_tests,
            breakdown=breakdown,
        )

    # ── Individual factors ─────────────────────────────────────────────────────

    @staticmethod
    def _size_risk(diff: str, files: list[str]) -> RiskBreakdown:
        lines = diff.count("\n")
        file_count = len(files)
        # Score: <100 lines = 1, 100-300 = 3, 300-600 = 6, >600 = 9
        if lines > 800:
            score, note = 9.0, f"{lines} lines changed — very large PR"
        elif lines > 400:
            score, note = 6.5, f"{lines} lines across {file_count} files — large PR"
        elif lines > 150:
            score, note = 3.5, f"{lines} lines across {file_count} files — medium PR"
        else:
            score, note = 1.0, f"{lines} lines — small, focused change"
        return RiskBreakdown("size", score, PRRiskScorer._WEIGHTS["size"], note,
                             [f"{lines} diff lines", f"{file_count} files"])

    @staticmethod
    def _churn_risk(files: list[str], churn: dict[str, ChurnData]) -> RiskBreakdown:
        if not files or not churn:
            return RiskBreakdown("churn", 0.0, PRRiskScorer._WEIGHTS["churn"],
                                 "No churn history available", [])
        scores = []
        evidence = []
        for fp in files:
            if fp in churn:
                cd = churn[fp]
                scores.append(cd.churn_score)
                if cd.churn_score > 5:
                    evidence.append(f"{fp}: {cd.commits_30d} commits/30d, {cd.bug_fix_commits} bugs")
        if not scores:
            return RiskBreakdown("churn", 0.0, PRRiskScorer._WEIGHTS["churn"],
                                 "Changed files have no churn history", [])
        avg = sum(scores) / len(scores)
        note = f"Avg churn score {avg:.1f} across {len(scores)} files"
        return RiskBreakdown("churn", round(min(10, avg), 2),
                             PRRiskScorer._WEIGHTS["churn"], note, evidence[:4])

    @staticmethod
    def _critical_file_risk(files: list[str], pr_title: str) -> RiskBreakdown:
        max_score = 0.0
        evidence = []
        for fp in files:
            for pattern, risk_val in _CRITICAL_PATTERNS:
                if pattern.search(fp):
                    max_score = max(max_score, risk_val)
                    evidence.append(f"{fp} matches '{pattern.pattern[:30]}'")
        # Also scan PR title
        for pattern, risk_val in _CRITICAL_PATTERNS:
            if pattern.search(pr_title):
                max_score = max(max_score, risk_val * 0.7)

        note = (f"Touches critical file(s): {', '.join(evidence[:2])}"
                if evidence else "No critical files detected")
        return RiskBreakdown("critical_file", round(max_score, 1),
                             PRRiskScorer._WEIGHTS["critical_file"], note, evidence[:3])

    @staticmethod
    def _test_coverage_risk(diff: str, files: list[str]) -> RiskBreakdown:
        source_files = [f for f in files if not _TEST_PATTERNS.search(f)]
        test_files   = [f for f in files if _TEST_PATTERNS.search(f)]

        if not source_files:
            return RiskBreakdown("test_coverage", 0.0, PRRiskScorer._WEIGHTS["test_coverage"],
                                 "Only test files changed", [])
        if test_files:
            ratio = len(test_files) / max(len(source_files), 1)
            score = max(0.0, 4.0 - ratio * 4.0)   # 0 tests relative = 4, 1:1 = 0
            note  = f"{len(test_files)} test file(s) for {len(source_files)} source file(s)"
        else:
            score = 7.0
            note  = f"{len(source_files)} source file(s) changed with no test changes"
        return RiskBreakdown("test_coverage", round(score, 1),
                             PRRiskScorer._WEIGHTS["test_coverage"], note,
                             source_files[:3])

    @staticmethod
    def _author_risk(author: Optional[str], quality_score: Optional[float]) -> RiskBreakdown:
        if quality_score is None:
            return RiskBreakdown("author", 3.0, PRRiskScorer._WEIGHTS["author"],
                                 "No historical quality data for this author", [])
        # quality_score from brain: 0–10, higher = better → invert for risk
        risk = round(max(0.0, 10.0 - quality_score), 1)
        note = (f"{author or 'Author'} avg quality score: {quality_score:.1f}/10 "
                f"→ author risk: {risk:.1f}/10")
        return RiskBreakdown("author", risk, PRRiskScorer._WEIGHTS["author"], note)

    @staticmethod
    def _complexity_risk(diff: str) -> RiskBreakdown:
        hits = []
        for pattern in _COMPLEXITY_SIGNALS:
            found = pattern.findall(diff)
            if found:
                hits.append(pattern.pattern[:40])
        score = min(10.0, len(hits) * 2.5)
        note  = (f"Complexity signals: {', '.join(hits[:3])}"
                 if hits else "No high-complexity patterns detected")
        return RiskBreakdown("complexity", round(score, 1),
                             PRRiskScorer._WEIGHTS["complexity"], note, hits[:4])
