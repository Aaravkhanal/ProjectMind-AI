"""
DNA Generator — writes .projectmind/ files from extracted ProjectDNA.
LLM-enhanced architecture summary is optional (requires API key).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.core.dna.extractor import ProjectDNA


PROJECTMIND_DIR = ".projectmind"


class DNAGenerator:
    def __init__(self, dna: ProjectDNA, llm_summary: Optional[str] = None):
        self.dna = dna
        self.llm_summary = llm_summary
        self.pm_dir = Path(dna.project_path) / PROJECTMIND_DIR

    def generate(self) -> Path:
        self.pm_dir.mkdir(exist_ok=True)
        (self.pm_dir / "embeddings").mkdir(exist_ok=True)
        (self.pm_dir / "knowledge_graph").mkdir(exist_ok=True)

        self._write_architecture()
        self._write_dependencies()
        self._write_coding_style()
        self._write_patterns()
        self._write_components()
        self._write_timeline()
        self._write_empty("mistakes.md", "# Mistakes & Known Issues\n\n_No entries yet. Add errors and their fixes here._\n")
        self._write_empty("decisions.md", "# Architectural Decisions\n\n_No decisions recorded yet._\n")
        self._write_empty("prompts.md", "# Saved Prompts\n\n_Successful prompts will be stored here._\n")
        self._init_memory_db()

        return self.pm_dir

    # ------------------------------------------------------------------
    # Individual file writers
    # ------------------------------------------------------------------

    def _write_architecture(self):
        dna = self.dna
        lines = [
            "# Architecture\n",
            f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n",
            f"**Project:** {Path(dna.project_path).name}\n",
            "",
            "## Overview\n",
        ]

        if self.llm_summary:
            lines.append(self.llm_summary)
        else:
            lines.append(
                f"A **{dna.language}** project using **{', '.join(dna.frameworks) or 'no detected frameworks'}**. "
                f"Architecture pattern: **{dna.architecture_pattern}**. "
                f"Source files: {dna.source_files} / {dna.total_files} total.\n"
            )

        lines += [
            "",
            "## Stack\n",
            f"- **Language:** {dna.language}",
            f"- **Frameworks:** {', '.join(dna.frameworks) or 'none detected'}",
            f"- **Architecture:** {dna.architecture_pattern}",
            f"- **Package Manager:** {dna.package_manager or 'unknown'}",
            f"- **Database:** {dna.database or 'none detected'}",
            f"- **Authentication:** {dna.auth_strategy or 'none detected'}",
            f"- **API Style:** {dna.api_style or 'none detected'}",
            f"- **Testing:** {dna.test_framework or 'none detected'}",
            f"- **Deployment:** {', '.join(dna.deployment) or 'none detected'}",
            "",
            "## Folder Structure\n",
            "```",
            *dna.folder_structure,
            "```",
            "",
            "## Entry Points\n",
*([f"- `{ep}`" for ep in dna.entry_points] or ["_None detected_"]),
        ]

        (self.pm_dir / "architecture.md").write_text("\n".join(lines))

    def _write_dependencies(self):
        dna = self.dna
        lines = [
            "# Dependencies\n",
            f"**Language:** {dna.language}  |  **Package Manager:** {dna.package_manager or 'unknown'}\n",
            "",
            "## Runtime Dependencies\n",
        ]
        if dna.dependencies:
            lines += [f"- `{k}`: {v}" for k, v in sorted(dna.dependencies.items())]
        else:
            lines.append("_None detected_")

        if dna.dev_dependencies:
            lines += ["", "## Dev Dependencies\n"]
            lines += [f"- `{k}`: {v}" for k, v in sorted(dna.dev_dependencies.items())]

        lines += [
            "",
            "## Detected Frameworks\n",
*([f"- {fw}" for fw in dna.frameworks] or ["_None_"]),
        ]
        (self.pm_dir / "dependencies.md").write_text("\n".join(lines))

    def _write_coding_style(self):
        dna = self.dna
        style_notes: list[str] = []

        if dna.language == "python":
            style_notes += [
                "- Use type hints on all function signatures",
                "- Prefer dataclasses or Pydantic models for structured data",
                "- Use pathlib.Path instead of os.path for file operations",
                "- Follow PEP 8 naming: snake_case for functions/variables, PascalCase for classes",
            ]
            if "FastAPI" in dna.frameworks:
                style_notes += [
                    "- Define request/response models with Pydantic BaseModel",
                    "- Use async def for route handlers",
                    "- Group routes in APIRouter, register on the app in main.py",
                ]
            if "LangChain" in dna.frameworks:
                style_notes += [
                    "- Build chains using LCEL (pipe operator |)",
                    "- Load prompts from .md template files, not inline strings",
                ]
        elif dna.language in ("typescript", "javascript"):
            style_notes += [
                "- Prefer const over let; never use var",
                "- Use async/await over raw Promise chains",
                "- Export named exports, avoid default exports for utilities",
            ]
            if "React" in dna.frameworks or "Next.js" in dna.frameworks:
                style_notes += [
                    "- Use functional components with hooks, no class components",
                    "- Co-locate component styles and tests with the component file",
                ]
            if "Next.js" in dna.frameworks:
                style_notes += [
                    "- Use Server Components by default; add 'use client' only when needed",
                    "- Use Server Actions for form submissions and data mutations",
                ]
            if "Prisma" in dna.frameworks:
                style_notes += [
                    "- Never use raw SQL — always use Prisma client methods",
                    "- Run migrations before deploying schema changes",
                ]

        lines = [
            "# Coding Style\n",
            "_Auto-detected from project structure and dependencies. Add project-specific rules below._\n",
            "",
            "## Detected Conventions\n",
*(style_notes or ["_No specific conventions auto-detected._"]),
            "",
            "## Project-Specific Rules\n",
            "_Add your team's rules here:_\n",
            "- [ ] Example: always wrap external API calls in try/catch",
        ]
        (self.pm_dir / "coding_style.md").write_text("\n".join(lines))

    def _write_patterns(self):
        dna = self.dna
        pattern_desc = {
            "service-repository": "Business logic lives in Services; data access is encapsulated in Repositories. Controllers/Routes delegate to Services only.",
            "mvc": "Model-View-Controller separation. Models own data, Views own rendering, Controllers handle HTTP logic.",
            "component-based": "UI is composed of reusable, isolated components. State is managed locally or via a global store.",
            "clean-architecture": "Domain logic is independent of frameworks. Dependency arrows point inward: entities ← use cases ← adapters ← infrastructure.",
            "microservices": "The system is split into independent deployable services communicating over HTTP or messaging.",
            "event-driven": "Components communicate through events. Publishers emit events; subscribers react asynchronously.",
            "hexagonal": "Core domain is surrounded by ports (interfaces) and adapters (implementations). The domain never knows about the outside world.",
        }

        lines = [
            "# Patterns\n",
            f"**Detected architecture pattern:** `{dna.architecture_pattern}`\n",
            "",
        ]
        desc = pattern_desc.get(dna.architecture_pattern)
        if desc:
            lines.append(f"_{desc}_\n")

        lines += [
            "",
            "## Design Patterns in Use\n",
            "_This section is populated as patterns are observed during development._\n",
            "| Pattern | Location | Notes |",
            "|---------|----------|-------|",
            "| (add patterns here) | | |",
        ]
        (self.pm_dir / "patterns.md").write_text("\n".join(lines))

    def _write_components(self):
        dna = self.dna
        lines = [
            "# Components\n",
            "_Auto-detected top-level modules and directories._\n",
            "",
            "## Module Map\n",
        ]
        for entry in dna.folder_structure:
            lines.append(f"- `{entry.strip()}/`")

        lines += [
            "",
            "## Key Components\n",
            "_Populated automatically as the knowledge graph is built (Phase 5)._\n",
            "| Component | Type | Responsibilities | Dependencies |",
            "|-----------|------|-----------------|--------------|",
        ]
        (self.pm_dir / "components.md").write_text("\n".join(lines))

    def _write_timeline(self):
        lines = [
            "# Project Timeline\n",
            "_Derived from git log. Shows what was built and when._\n",
            "",
        ]
        try:
            result = subprocess.run(
                ["git", "log", "--pretty=format:%ad | %s", "--date=short", "--max-count=50"],
                cwd=self.dna.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines.append("## Commit History (last 50)\n")
                lines.append("| Date | Commit |")
                lines.append("|------|--------|")
                for entry in result.stdout.strip().splitlines():
                    parts = entry.split(" | ", 1)
                    if len(parts) == 2:
                        lines.append(f"| {parts[0]} | {parts[1]} |")
            else:
                lines.append("_No git history found._")
        except Exception:
            lines.append("_Could not read git history._")

        (self.pm_dir / "timeline.md").write_text("\n".join(lines))

    def _write_empty(self, filename: str, content: str):
        path = self.pm_dir / filename
        if not path.exists():
            path.write_text(content)

    def _init_memory_db(self):
        db_path = self.pm_dir / "memory.db"
        if not db_path.exists():
            try:
                from backend.core.memory.store import MemoryStore
                store = MemoryStore(str(db_path))
                store.init_db()
            except Exception:
                db_path.touch()
