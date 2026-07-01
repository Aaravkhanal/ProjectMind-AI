"""
Phase 21 — Architecture Memory.

Scans a repository and builds a persistent JSON snapshot of its technical shape:
languages, frameworks, libraries, patterns, conventions, services, deployment stack.
Stored at .brain/architecture/state.json inside the project.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".swift": "Swift",
    ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell", ".r": "R", ".jl": "Julia",
}

_FRAMEWORK_INDICATORS: dict[str, list[str]] = {
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Express.js": ["express"],
    "Next.js": ["next", "nextjs"],
    "React": ["react", "react-dom"],
    "Vue.js": ["vue"],
    "Angular": ["@angular/core"],
    "Svelte": ["svelte"],
    "Spring Boot": ["spring-boot-starter"],
    "LangChain": ["langchain"],
    "LangGraph": ["langgraph"],
    "LiteLLM": ["litellm"],
    "SQLModel": ["sqlmodel"],
    "SQLAlchemy": ["sqlalchemy"],
    "Pydantic": ["pydantic"],
    "Celery": ["celery"],
    "Pytest": ["pytest"],
    "Jest": ["jest"],
    "Tailwind CSS": ["tailwindcss"],
}

_PATTERN_INDICATORS: dict[str, list[str]] = {
    "REST API": ["APIRouter", "app.get", "app.post", "router.get"],
    "CQRS": ["CommandHandler", "QueryHandler", "Command", "Query"],
    "Repository Pattern": ["Repository", "IRepository"],
    "Factory Pattern": ["Factory", "create_", "make_"],
    "Dependency Injection": ["Depends(", "inject"],
    "Event Sourcing": ["EventStore", "DomainEvent"],
    "LCEL Chains": [" | ", "RunnablePassthrough", "RunnableLambda"],
    "Multi-Agent": ["LangGraph", "StateGraph", "AgentExecutor"],
    "BYOK": ["Fernet", "api_key", "BYOK"],
}

_DEPLOYMENT_INDICATORS: dict[str, str] = {
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "fly.toml": "Fly.io",
    "railway.json": "Railway",
    "render.yaml": "Render",
    "vercel.json": "Vercel",
    "netlify.toml": "Netlify",
    ".github/workflows": "GitHub Actions",
    "k8s": "Kubernetes",
    "helm": "Helm",
}


def _empty_state() -> dict[str, Any]:
    return {
        "languages": [],
        "frameworks": [],
        "libraries": [],
        "patterns": [],
        "anti_patterns": [],
        "services": [],
        "apis": [],
        "databases": [],
        "deployment": [],
        "testing": [],
        "security": [],
        "conventions": [],
        "architecture_style": "",
        "repository_type": "",
        "file_count": 0,
        "total_loc": 0,
    }


class ArchitectureMemory:
    def __init__(self, brain_dir: Path):
        self._dir = brain_dir / "architecture"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._dir / "state.json"

    # ── public API ─────────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except Exception:
                pass
        return _empty_state()

    def scan(self, project_path: str) -> dict[str, Any]:
        root = Path(project_path).resolve()
        state = _empty_state()

        self._detect_languages(root, state)
        self._detect_frameworks(root, state)
        self._detect_patterns(root, state)
        self._detect_deployment(root, state)
        self._detect_databases(root, state)
        self._detect_testing(root, state)
        self._infer_architecture_style(state)
        self._infer_repo_type(root, state)

        self._state_file.write_text(json.dumps(state, indent=2))
        return state

    # ── detection helpers ──────────────────────────────────────────────────────

    def _detect_languages(self, root: Path, state: dict) -> None:
        counts: dict[str, int] = {}
        loc_total = 0
        skip = {".venv", "node_modules", ".git", "__pycache__", "dist", ".next", "build"}
        for f in root.rglob("*"):
            if f.is_file() and not any(p in f.parts for p in skip):
                lang = _LANGUAGE_EXTENSIONS.get(f.suffix.lower())
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
                    try:
                        loc_total += sum(1 for _ in f.open("rb"))
                    except Exception:
                        pass
        state["languages"] = sorted(counts, key=lambda k: counts[k], reverse=True)
        state["file_count"] = sum(counts.values())
        state["total_loc"] = loc_total

    def _detect_frameworks(self, root: Path, state: dict) -> None:
        dep_text = self._read_dependency_manifests(root)
        found: list[str] = []
        libs: set[str] = set()

        for fw, keywords in _FRAMEWORK_INDICATORS.items():
            if any(kw in dep_text for kw in keywords):
                found.append(fw)

        # Collect raw library names from pyproject.toml
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text().splitlines():
                m = re.match(r'^(\S+)\s*=', line.strip())
                if m and "=" in line and not line.strip().startswith("["):
                    libs.add(m.group(1).strip('"').strip("'"))

        # Collect from package.json
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                for section in ("dependencies", "devDependencies"):
                    libs.update(data.get(section, {}).keys())
            except Exception:
                pass

        state["frameworks"] = found
        state["libraries"] = sorted(libs)[:50]  # cap at 50

    def _detect_patterns(self, root: Path, state: dict) -> None:
        all_source = self._sample_source_code(root)
        found: list[str] = []
        for pattern, indicators in _PATTERN_INDICATORS.items():
            if any(ind in all_source for ind in indicators):
                found.append(pattern)
        state["patterns"] = found

    def _detect_deployment(self, root: Path, state: dict) -> None:
        found: list[str] = []
        for indicator, name in _DEPLOYMENT_INDICATORS.items():
            if (root / indicator).exists() and name not in found:
                found.append(name)
        state["deployment"] = found

    def _detect_databases(self, root: Path, state: dict) -> None:
        dep_text = self._read_dependency_manifests(root)
        db_map = {
            "sqlite": "SQLite",
            "postgresql": "PostgreSQL",
            "psycopg": "PostgreSQL",
            "mysql": "MySQL",
            "mongodb": "MongoDB",
            "redis": "Redis",
            "chromadb": "ChromaDB",
            "qdrant": "Qdrant",
            "lancedb": "LanceDB",
            "pinecone": "Pinecone",
            "weaviate": "Weaviate",
        }
        found: list[str] = []
        for key, name in db_map.items():
            if key in dep_text and name not in found:
                found.append(name)
        state["databases"] = found

    def _detect_testing(self, root: Path, state: dict) -> None:
        dep_text = self._read_dependency_manifests(root)
        found: list[str] = []
        test_map = {
            "pytest": "pytest",
            "unittest": "unittest",
            "jest": "Jest",
            "vitest": "Vitest",
            "mocha": "Mocha",
            "cypress": "Cypress",
            "playwright": "Playwright",
        }
        for key, name in test_map.items():
            if key in dep_text:
                found.append(name)
        state["testing"] = found

    def _infer_architecture_style(self, state: dict) -> None:
        patterns = state.get("patterns", [])
        if "Multi-Agent" in patterns and "LCEL Chains" in patterns:
            state["architecture_style"] = "Multi-Agent AI Orchestration"
        elif "CQRS" in patterns and "Event Sourcing" in patterns:
            state["architecture_style"] = "CQRS + Event Sourcing"
        elif "REST API" in patterns:
            state["architecture_style"] = "Layered REST API"
        elif "Repository Pattern" in patterns:
            state["architecture_style"] = "Repository Pattern"

    def _infer_repo_type(self, root: Path, state: dict) -> None:
        frameworks = state.get("frameworks", [])
        if "LangChain" in frameworks or "LangGraph" in frameworks:
            state["repository_type"] = "AI/LLM Application"
        elif any(f in frameworks for f in ["FastAPI", "Django", "Flask"]):
            state["repository_type"] = "Backend API"
        elif any(f in frameworks for f in ["Next.js", "React", "Vue.js"]):
            state["repository_type"] = "Frontend Application"
        elif (root / "pyproject.toml").exists():
            state["repository_type"] = "Python Package"
        else:
            state["repository_type"] = "General Software Project"

    # ── file helpers ───────────────────────────────────────────────────────────

    def _read_dependency_manifests(self, root: Path) -> str:
        manifests = [
            "pyproject.toml", "requirements.txt", "package.json",
            "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
        ]
        parts: list[str] = []
        for m in manifests:
            p = root / m
            if p.exists():
                try:
                    parts.append(p.read_text().lower())
                except Exception:
                    pass
        return "\n".join(parts)

    def _sample_source_code(self, root: Path) -> str:
        skip = {".venv", "node_modules", ".git", "__pycache__", "dist"}
        parts: list[str] = []
        count = 0
        for f in root.rglob("*.py"):
            if count >= 30:
                break
            if any(p in f.parts for p in skip):
                continue
            try:
                parts.append(f.read_text(errors="ignore")[:2000])
                count += 1
            except Exception:
                pass
        return "\n".join(parts)
