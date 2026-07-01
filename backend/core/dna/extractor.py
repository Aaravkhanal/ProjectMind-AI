"""
Project DNA Extractor — heuristic-based, zero-LLM, zero-dependency analysis.
Detects language, frameworks, architecture patterns, and project structure
by reading config files and the directory tree.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProjectDNA:
    project_path: str
    language: str = "unknown"
    frameworks: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)
    folder_structure: list[str] = field(default_factory=list)
    architecture_pattern: str = "unknown"
    entry_points: list[str] = field(default_factory=list)
    has_tests: bool = False
    test_framework: Optional[str] = None
    database: Optional[str] = None
    auth_strategy: Optional[str] = None
    deployment: list[str] = field(default_factory=list)
    api_style: Optional[str] = None
    package_manager: Optional[str] = None
    python_version: Optional[str] = None
    node_version: Optional[str] = None
    git_remote: Optional[str] = None
    total_files: int = 0
    source_files: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "htmlcov", ".tox",
}

FRAMEWORK_SIGNALS: dict[str, dict[str, list[str]]] = {
    "python": {
        "FastAPI": ["fastapi"],
        "Django": ["django"],
        "Flask": ["flask"],
        "Streamlit": ["streamlit"],
        "LangChain": ["langchain", "langchain-core", "langchain-community"],
        "PyTorch": ["torch"],
        "TensorFlow": ["tensorflow"],
        "Pydantic": ["pydantic"],
        "SQLAlchemy": ["sqlalchemy", "sqlmodel"],
        "Celery": ["celery"],
        "Pytest": ["pytest"],
    },
    "javascript": {
        "React": ["react"],
        "Next.js": ["next"],
        "Vue": ["vue"],
        "Express": ["express"],
        "NestJS": ["@nestjs/core"],
        "Vite": ["vite"],
        "Jest": ["jest"],
        "Vitest": ["vitest"],
        "Prisma": ["@prisma/client", "prisma"],
    },
    "typescript": {
        "React": ["react"],
        "Next.js": ["next"],
        "Vue": ["vue"],
        "Express": ["express"],
        "NestJS": ["@nestjs/core"],
        "Vite": ["vite"],
        "Jest": ["jest"],
        "Vitest": ["vitest"],
        "Prisma": ["@prisma/client", "prisma"],
    },
}

DATABASE_SIGNALS = {
    "postgresql": ["psycopg2", "asyncpg", "psycopg", "pg", "@prisma/client"],
    "mysql": ["pymysql", "aiomysql", "mysql2"],
    "sqlite": ["sqlite3", "aiosqlite", "sqlmodel"],
    "mongodb": ["pymongo", "motor", "mongoose"],
    "redis": ["redis", "aioredis", "ioredis"],
    "elasticsearch": ["elasticsearch", "@elastic/elasticsearch"],
}

AUTH_SIGNALS = {
    "JWT": ["python-jose", "pyjwt", "jsonwebtoken", "jose"],
    "OAuth2": ["authlib", "python-social-auth", "passport"],
    "Session": ["flask-login", "django.contrib.sessions", "express-session"],
    "Supabase": ["supabase"],
    "Auth0": ["auth0"],
    "NextAuth": ["next-auth"],
}

ARCH_PATTERNS = {
    "layered-api":        ["api", "core", "routes", "schemas", "backend"],
    "service-repository": ["services", "repositories", "service", "repository"],
    "mvc":                ["controllers", "models", "views", "controller", "model", "view"],
    "clean-architecture": ["usecases", "entities", "adapters", "use_cases"],
    "component-based":    ["components", "pages", "layouts", "hooks"],
    "microservices":      ["services", "gateway", "api-gateway"],
    "event-driven":       ["events", "handlers", "subscribers", "publishers"],
    "hexagonal":          ["ports", "adapters", "domain", "infrastructure"],
}

TEST_SIGNALS = {
    "pytest": ["pytest", "conftest.py", "test_*.py"],
    "jest": ["jest", "*.test.ts", "*.spec.ts", "*.test.js", "*.spec.js"],
    "vitest": ["vitest"],
    "unittest": ["unittest"],
    "go-test": ["_test.go"],
}


class DNAExtractor:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()

    def extract(self) -> ProjectDNA:
        dna = ProjectDNA(project_path=str(self.root))
        dna.language = self._detect_language()
        dna.package_manager = self._detect_package_manager(dna.language)
        dna.dependencies, dna.dev_dependencies = self._extract_deps(dna.language)
        dna.frameworks = self._detect_frameworks(dna.language, dna.dependencies, dna.dev_dependencies)
        dna.folder_structure = self._map_folder_structure()
        dna.architecture_pattern = self._detect_arch_pattern(dna.folder_structure)
        dna.entry_points = self._find_entry_points(dna.language)
        dna.has_tests, dna.test_framework = self._detect_tests(dna.language, dna.dependencies, dna.dev_dependencies)
        dna.database = self._detect_database(dna.dependencies, dna.dev_dependencies)
        dna.auth_strategy = self._detect_auth(dna.dependencies, dna.dev_dependencies)
        dna.deployment = self._detect_deployment()
        dna.api_style = self._detect_api_style(dna.frameworks, dna.folder_structure)
        dna.python_version = self._python_version()
        dna.git_remote = self._git_remote()
        dna.total_files, dna.source_files = self._count_files(dna.language)
        return dna

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_language(self) -> str:
        if (self.root / "pyproject.toml").exists() or (self.root / "setup.py").exists() or (self.root / "requirements.txt").exists():
            return "python"
        if (self.root / "package.json").exists():
            if (self.root / "tsconfig.json").exists():
                return "typescript"
            src = self.root / "src"
            if src.exists() and any(src.rglob("*.ts")):
                return "typescript"
            return "javascript"
        if (self.root / "go.mod").exists():
            return "go"
        if (self.root / "Cargo.toml").exists():
            return "rust"
        if (self.root / "pom.xml").exists() or (self.root / "build.gradle").exists():
            return "java"
        if (self.root / "mix.exs").exists():
            return "elixir"
        return "unknown"

    # ------------------------------------------------------------------
    # Package manager
    # ------------------------------------------------------------------

    def _detect_package_manager(self, language: str) -> Optional[str]:
        if language == "python":
            if (self.root / "pyproject.toml").exists():
                return "poetry" if (self.root / "poetry.lock").exists() else "pip"
            if (self.root / "Pipfile").exists():
                return "pipenv"
            return "pip"
        if language in ("javascript", "typescript"):
            if (self.root / "pnpm-lock.yaml").exists():
                return "pnpm"
            if (self.root / "yarn.lock").exists():
                return "yarn"
            return "npm"
        if language == "rust":
            return "cargo"
        if language == "go":
            return "go modules"
        return None

    # ------------------------------------------------------------------
    # Dependency extraction
    # ------------------------------------------------------------------

    def _extract_deps(self, language: str) -> tuple[dict[str, str], dict[str, str]]:
        if language == "python":
            return self._python_deps()
        if language in ("javascript", "typescript"):
            return self._js_deps()
        if language == "go":
            return self._go_deps()
        if language == "rust":
            return self._rust_deps()
        return {}, {}

    def _python_deps(self) -> tuple[dict[str, str], dict[str, str]]:
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            poetry = data.get("tool", {}).get("poetry", {})
            deps = {k: str(v) for k, v in poetry.get("dependencies", {}).items() if k != "python"}
            dev_deps = {k: str(v) for k, v in poetry.get("group", {}).get("dev", {}).get("dependencies", {}).items()}
            return deps, dev_deps

        req = self.root / "requirements.txt"
        if req.exists():
            deps: dict[str, str] = {}
            for line in req.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("==")
                    deps[parts[0].lower()] = parts[1] if len(parts) > 1 else "*"
            return deps, {}
        return {}, {}

    def _js_deps(self) -> tuple[dict[str, str], dict[str, str]]:
        pkg = self.root / "package.json"
        if not pkg.exists():
            return {}, {}
        data = json.loads(pkg.read_text())
        return (
            {k: str(v) for k, v in data.get("dependencies", {}).items()},
            {k: str(v) for k, v in data.get("devDependencies", {}).items()},
        )

    def _go_deps(self) -> tuple[dict[str, str], dict[str, str]]:
        gomod = self.root / "go.mod"
        if not gomod.exists():
            return {}, {}
        deps: dict[str, str] = {}
        for line in gomod.read_text().splitlines():
            line = line.strip()
            if line.startswith("require") or line.startswith(")") or line.startswith("module") or line.startswith("go "):
                continue
            parts = line.split()
            if len(parts) == 2:
                deps[parts[0]] = parts[1]
        return deps, {}

    def _rust_deps(self) -> tuple[dict[str, str], dict[str, str]]:
        cargo = self.root / "Cargo.toml"
        if not cargo.exists():
            return {}, {}
        with open(cargo, "rb") as f:
            data = tomllib.load(f)
        deps = {k: str(v) for k, v in data.get("dependencies", {}).items()}
        dev_deps = {k: str(v) for k, v in data.get("dev-dependencies", {}).items()}
        return deps, dev_deps

    # ------------------------------------------------------------------
    # Framework detection
    # ------------------------------------------------------------------

    def _detect_frameworks(
        self,
        language: str,
        deps: dict[str, str],
        dev_deps: dict[str, str],
    ) -> list[str]:
        signals = FRAMEWORK_SIGNALS.get(language, {})
        all_deps = {k.lower() for k in {**deps, **dev_deps}}
        found = []
        for framework, keywords in signals.items():
            if any(k.lower() in all_deps for k in keywords):
                found.append(framework)
        return found

    # ------------------------------------------------------------------
    # Folder structure
    # ------------------------------------------------------------------

    def _map_folder_structure(self) -> list[str]:
        dirs = []
        for item in sorted(self.root.iterdir()):
            if item.is_dir() and item.name not in IGNORE_DIRS and not item.name.startswith("."):
                dirs.append(item.name)
                for sub in sorted(item.iterdir()):
                    if sub.is_dir() and sub.name not in IGNORE_DIRS and not sub.name.startswith("."):
                        dirs.append(f"  {item.name}/{sub.name}")
        return dirs

    # ------------------------------------------------------------------
    # Architecture pattern
    # ------------------------------------------------------------------

    def _detect_arch_pattern(self, folders: list[str]) -> str:
        flat = " ".join(f.strip().lower() for f in folders)
        scores: dict[str, int] = {}
        for pattern, keywords in ARCH_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in flat)
            if score > 0:
                scores[pattern] = score
        if not scores:
            return "unknown"
        return max(scores, key=lambda k: scores[k])

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def _find_entry_points(self, language: str) -> list[str]:
        candidates = []
        if language == "python":
            for name in ["main.py", "app.py", "server.py", "run.py", "manage.py"]:
                for f in self.root.rglob(name):
                    if not any(p in IGNORE_DIRS for p in f.parts):
                        candidates.append(str(f.relative_to(self.root)))
        elif language in ("javascript", "typescript"):
            pkg = self.root / "package.json"
            if pkg.exists():
                data = json.loads(pkg.read_text())
                main = data.get("main") or data.get("module")
                if main:
                    candidates.append(main)
                scripts = data.get("scripts", {})
                for key in ("start", "dev", "serve"):
                    if key in scripts:
                        candidates.append(f"npm run {key}: {scripts[key]}")
        return candidates[:8]

    # ------------------------------------------------------------------
    # Testing
    # ------------------------------------------------------------------

    def _detect_tests(
        self,
        language: str,
        deps: dict[str, str],
        dev_deps: dict[str, str],
    ) -> tuple[bool, Optional[str]]:
        all_deps_lower = {k.lower() for k in {**deps, **dev_deps}}
        test_dirs = {"tests", "test", "__tests__", "spec"}
        has_test_dir = any((self.root / d).exists() for d in test_dirs)
        has_test_files = bool(list(self.root.rglob("test_*.py"))[:1]) or \
                         bool(list(self.root.rglob("*.test.ts"))[:1]) or \
                         bool(list(self.root.rglob("*.spec.ts"))[:1]) or \
                         bool(list(self.root.rglob("*_test.go"))[:1])
        has_tests = has_test_dir or has_test_files

        framework: Optional[str] = None
        if "pytest" in all_deps_lower or language == "python":
            if has_tests:
                framework = "pytest"
        if "jest" in all_deps_lower:
            framework = "Jest"
        if "vitest" in all_deps_lower:
            framework = "Vitest"
        return has_tests, framework

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _detect_database(
        self, deps: dict[str, str], dev_deps: dict[str, str]
    ) -> Optional[str]:
        all_deps_lower = {k.lower() for k in {**deps, **dev_deps}}
        for db, signals in DATABASE_SIGNALS.items():
            if any(s.lower() in all_deps_lower for s in signals):
                return db
        return None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _detect_auth(
        self, deps: dict[str, str], dev_deps: dict[str, str]
    ) -> Optional[str]:
        all_deps_lower = {k.lower() for k in {**deps, **dev_deps}}
        for strategy, signals in AUTH_SIGNALS.items():
            if any(s.lower() in all_deps_lower for s in signals):
                return strategy
        return None

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def _detect_deployment(self) -> list[str]:
        signals = []
        checks = {
            "Docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
            "Kubernetes": ["k8s", "kubernetes", "helm"],
            "GitHub Actions": [".github/workflows"],
            "GitLab CI": [".gitlab-ci.yml"],
            "Vercel": ["vercel.json", ".vercel"],
            "Railway": ["railway.json"],
            "Render": ["render.yaml"],
            "AWS": ["serverless.yml", "cdk.json", "aws-exports.js"],
            "Terraform": ["main.tf", "*.tf"],
        }
        for platform, files in checks.items():
            for f in files:
                if "*" in f:
                    if list(self.root.glob(f)):
                        signals.append(platform)
                        break
                elif (self.root / f).exists():
                    signals.append(platform)
                    break
        return signals

    # ------------------------------------------------------------------
    # API style
    # ------------------------------------------------------------------

    def _detect_api_style(
        self, frameworks: list[str], folders: list[str]
    ) -> Optional[str]:
        flat = " ".join(f.strip().lower() for f in folders)
        if "FastAPI" in frameworks or "Express" in frameworks or "NestJS" in frameworks:
            if "graphql" in flat or "schema.graphql" in flat:
                return "GraphQL"
            return "REST"
        if "Next.js" in frameworks:
            if "graphql" in flat:
                return "GraphQL + REST"
            return "REST (Next.js API routes)"
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _python_version(self) -> Optional[str]:
        pv = self.root / ".python-version"
        if pv.exists():
            return pv.read_text().strip()
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            return data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
        return None

    def _git_remote(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def _count_files(self, language: str) -> tuple[int, int]:
        ext_map = {
            "python": {".py"},
            "typescript": {".ts", ".tsx"},
            "javascript": {".js", ".jsx"},
            "go": {".go"},
            "rust": {".rs"},
        }
        source_exts = ext_map.get(language, set())
        total = 0
        source = 0
        for path in self.root.rglob("*"):
            if path.is_file() and not any(p in IGNORE_DIRS for p in path.parts):
                total += 1
                if path.suffix in source_exts:
                    source += 1
        return total, source
