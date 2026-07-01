"""
Dependency Risk Scorer.

For each declared dependency:
  1. Fetch PyPI / npm metadata (version, last release, maintainer count)
  2. Query OSV API for CVEs  (https://api.osv.dev — no auth needed)
  3. Count how many files in the project import this package (centrality)
  4. Compute a composite risk score

No API keys required — uses public APIs only.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.core.deps.scanner import scan


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CVE:
    id: str
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    summary: str


@dataclass
class DepRisk:
    name: str
    ecosystem: str
    declared_version: str
    latest_version: str
    days_since_release: int
    is_stale: bool             # no release in 365+ days
    has_maintainer: bool
    import_count: int          # how many project files import this
    cves: list[CVE]
    risk_score: float
    risk_level: str            # CRITICAL | HIGH | MEDIUM | LOW
    source: str                # which file declared it


_SEV_WEIGHT = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 10, "LOW": 5, "UNKNOWN": 3}
_STALE_DAYS = 365


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_dependencies(project_root: Path, timeout: float = 5.0) -> list[DepRisk]:
    """
    Scan declared deps, enrich with OSV + registry metadata, return risk list.
    Sorted by risk_score descending.
    """
    deps = scan(project_root)
    import_map = _build_import_map(project_root)
    results: list[DepRisk] = []

    for dep in deps:
        name = dep["name"]
        eco = dep["ecosystem"]
        try:
            if eco == "PyPI":
                meta = _pypi_meta(name, timeout)
            else:
                meta = _npm_meta(name, timeout)
            cves = _osv_query(name, eco, timeout)
            ic = import_map.get(name.lower().replace("-", "_"), 0) + \
                 import_map.get(name.lower().replace("_", "-"), 0)
            score = _compute_score(meta, cves, ic)
            results.append(DepRisk(
                name=name,
                ecosystem=eco,
                declared_version=dep["version"],
                latest_version=meta["latest_version"],
                days_since_release=meta["days_since_release"],
                is_stale=meta["days_since_release"] > _STALE_DAYS,
                has_maintainer=meta["has_maintainer"],
                import_count=ic,
                cves=cves,
                risk_score=score,
                risk_level=_level(score),
                source=dep["source"],
            ))
        except Exception:
            pass   # skip packages that error (network issues, private packages)

    return sorted(results, key=lambda r: -r.risk_score)


# ---------------------------------------------------------------------------
# Registry metadata fetchers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "projectmind/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _pypi_meta(name: str, timeout: float) -> dict:
    try:
        data = _fetch_json(f"https://pypi.org/pypi/{name}/json", timeout)
        info = data.get("info", {})
        releases = data.get("releases", {})
        latest = info.get("version", "?")
        # Find the most recent release date across all versions
        latest_date = _latest_release_date(releases)
        days = _days_since(latest_date) if latest_date else 9999
        maintainers = bool(info.get("maintainer") or info.get("author"))
        return {
            "latest_version": latest,
            "days_since_release": days,
            "has_maintainer": maintainers,
        }
    except Exception:
        return {"latest_version": "?", "days_since_release": 9999, "has_maintainer": False}


def _npm_meta(name: str, timeout: float) -> dict:
    try:
        safe = urllib.request.quote(name, safe="@/")
        data = _fetch_json(f"https://registry.npmjs.org/{safe}", timeout)
        latest = data.get("dist-tags", {}).get("latest", "?")
        times = data.get("time", {})
        latest_time = times.get(latest)
        days = _days_since(latest_time[:10]) if latest_time else 9999
        maintainers = bool(data.get("maintainers"))
        return {
            "latest_version": latest,
            "days_since_release": days,
            "has_maintainer": maintainers,
        }
    except Exception:
        return {"latest_version": "?", "days_since_release": 9999, "has_maintainer": False}


def _osv_query(name: str, ecosystem: str, timeout: float) -> list[CVE]:
    """Query OSV (Open Source Vulnerabilities) for known CVEs. No auth needed."""
    payload = json.dumps({"package": {"name": name, "ecosystem": ecosystem}}).encode()
    req = urllib.request.Request(
        "https://api.osv.dev/v1/query",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "projectmind/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:
        return []

    cves: list[CVE] = []
    for vuln in data.get("vulns", []):
        vid = vuln.get("id", "UNKNOWN")
        summary = vuln.get("summary", "")[:120]
        severity = _extract_severity(vuln)
        cves.append(CVE(id=vid, severity=severity, summary=summary))
    return cves


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _compute_score(meta: dict, cves: list[CVE], import_count: int) -> float:
    score = 0.0
    for cve in cves:
        score += _SEV_WEIGHT.get(cve.severity, 3)
    days = meta.get("days_since_release", 0)
    if days > _STALE_DAYS:
        score += (days - _STALE_DAYS) / 30  # +1 per extra month of staleness
    if not meta.get("has_maintainer"):
        score += 10
    score += import_count * 2   # centrality multiplier
    return round(score, 1)


def _level(score: float) -> str:
    if score >= 80:  return "CRITICAL"
    if score >= 40:  return "HIGH"
    if score >= 15:  return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_release_date(releases: dict) -> Optional[str]:
    """Find the most recent upload date across all release versions."""
    latest_ts: Optional[str] = None
    for _ver, files in releases.items():
        for f in files:
            upload = f.get("upload_time", "")
            if upload and (latest_ts is None or upload > latest_ts):
                latest_ts = upload[:10]
    return latest_ts


def _days_since(date_str: str) -> int:
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 9999


def _extract_severity(vuln: dict) -> str:
    # Try CVSS v3/v2 severity from severity list
    for sev in vuln.get("severity", []):
        score_str = sev.get("score", "")
        if "CVSS" in sev.get("type", ""):
            m = re.search(r"CVSS:[\d.]+/.*?/([^/]+)$", score_str)
            if m:
                return m.group(1).upper()
    # Fall back to database-specific severity fields
    for db in vuln.get("database_specific", {}).get("severity", []):
        if isinstance(db, str):
            return db.upper()
    # Check GHSA severity in aliases
    aliases = vuln.get("aliases", [])
    if any(a.startswith("CVE-") for a in aliases):
        return "UNKNOWN"
    return "UNKNOWN"


def _build_import_map(project_root: Path) -> dict[str, int]:
    """Count how many Python/JS files import each package name."""
    counts: dict[str, int] = {}
    ignore = {".venv", "venv", "node_modules", "__pycache__", ".git"}

    for ext, pattern in [(".py", r"(?:import|from)\s+([a-zA-Z0-9_]+)"),
                          (".ts", r"from\s+['\"]([a-zA-Z0-9_@\-/]+)['\"]"),
                          (".js", r"require\(['\"]([a-zA-Z0-9_@\-/]+)['\"]")]:
        for f in project_root.rglob(f"*{ext}"):
            if any(p in f.parts for p in ignore):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(pattern, text):
                    pkg = m.group(1).split("/")[0].lower()
                    counts[pkg] = counts.get(pkg, 0) + 1
            except Exception:
                pass
    return counts
