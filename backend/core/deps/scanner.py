"""
Dependency scanner — extracts declared dependencies from:
  - pyproject.toml  (Poetry [tool.poetry.dependencies] + [project.dependencies])
  - requirements.txt / requirements/*.txt
  - package.json (npm / yarn)
  - Pipfile

Returns a list of (name, version_spec, ecosystem) tuples.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


_IGNORE_PY = {"python", "pip", "setuptools", "wheel"}


def scan(project_root: Path) -> list[dict]:
    """
    Returns a list of:
      {"name": str, "version": str, "ecosystem": "PyPI" | "npm", "source": str}
    """
    deps: list[dict] = []
    root = Path(project_root)

    # pyproject.toml
    ppt = root / "pyproject.toml"
    if ppt.exists():
        deps.extend(_parse_pyproject(ppt))

    # requirements files
    for req_file in root.rglob("requirements*.txt"):
        if any(p in str(req_file) for p in [".venv", "node_modules", "__pycache__"]):
            continue
        deps.extend(_parse_requirements(req_file))

    # Pipfile
    pipfile = root / "Pipfile"
    if pipfile.exists():
        deps.extend(_parse_pipfile(pipfile))

    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        deps.extend(_parse_package_json(pkg_json))

    # Deduplicate by name+ecosystem, keeping first occurrence
    seen: set[str] = set()
    unique: list[dict] = []
    for d in deps:
        key = f"{d['ecosystem']}:{d['name'].lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_pyproject(path: Path) -> list[dict]:
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import]
        except ImportError:
            return _parse_pyproject_regex(path)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    deps: list[dict] = []

    # Poetry format
    poetry_deps = (
        data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    )
    for name, ver in poetry_deps.items():
        if name.lower() in _IGNORE_PY:
            continue
        version = ver if isinstance(ver, str) else (ver.get("version", "*") if isinstance(ver, dict) else "*")
        deps.append({"name": name, "version": version, "ecosystem": "PyPI", "source": str(path)})

    # PEP 621 format
    project_deps = data.get("project", {}).get("dependencies", [])
    for dep_str in project_deps:
        m = re.match(r"([A-Za-z0-9_\-\.]+)(.*)", dep_str.strip())
        if m:
            name = m.group(1)
            if name.lower() not in _IGNORE_PY:
                deps.append({"name": name, "version": m.group(2).strip() or "*", "ecosystem": "PyPI", "source": str(path)})

    return deps


def _parse_pyproject_regex(path: Path) -> list[dict]:
    """Fallback for when tomllib/tomli is not installed."""
    deps: list[dict] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Match lines like: requests = "^2.28.0" or requests = {version = "^2.28.0"}
    for m in re.finditer(r'^([a-zA-Z0-9_\-\.]+)\s*=\s*["\{]([^"\}\n]*)', text, re.MULTILINE):
        name = m.group(1)
        if name.lower() not in _IGNORE_PY and not name.startswith("["):
            deps.append({"name": name, "version": m.group(2), "ecosystem": "PyPI", "source": str(path)})
    return deps


def _parse_requirements(path: Path) -> list[dict]:
    deps: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip extras and environment markers
            line = re.sub(r"\[.*?\]", "", line)
            line = line.split(";")[0].strip()
            m = re.match(r"([A-Za-z0-9_\-\.]+)(.*)", line)
            if m:
                name = m.group(1)
                if name.lower() not in _IGNORE_PY:
                    deps.append({"name": name, "version": m.group(2).strip() or "*", "ecosystem": "PyPI", "source": str(path)})
    except Exception:
        pass
    return deps


def _parse_pipfile(path: Path) -> list[dict]:
    deps: list[dict] = []
    try:
        in_packages = False
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip() in ("[packages]", "[dev-packages]"):
                in_packages = True
                continue
            if line.startswith("[") and in_packages:
                in_packages = False
            if in_packages and "=" in line:
                m = re.match(r'([A-Za-z0-9_\-\.]+)\s*=\s*["\']?([^"\']+)', line)
                if m:
                    name = m.group(1)
                    if name.lower() not in _IGNORE_PY:
                        deps.append({"name": name, "version": m.group(2).strip(), "ecosystem": "PyPI", "source": str(path)})
    except Exception:
        pass
    return deps


def _parse_package_json(path: Path) -> list[dict]:
    deps: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name, version in data.get(section, {}).items():
                deps.append({"name": name, "version": version, "ecosystem": "npm", "source": str(path)})
    except Exception:
        pass
    return deps
