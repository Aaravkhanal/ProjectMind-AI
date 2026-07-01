"""
ProjectMind file watcher — keeps .projectmind/ in sync as you code.

Watches for source file changes, debounces bursts, then re-runs:
  1. DNA extraction    (always — fast, <50ms)
  2. Graph build       (on structural changes: new/deleted files, imports)
  3. Health analysis   (on any .py change)

Run via:  projectmind watch <path>
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


# Extensions that trigger a re-analysis
_WATCHED = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
# File patterns to ignore
_IGNORED = {"__pycache__", ".git", ".projectmind", "node_modules", ".venv", "venv", "dist", "build"}


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[str, str], None], debounce: float):
        super().__init__()
        self._on_change = on_change
        self._debounce = debounce
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._pending: list[tuple[str, str]] = []  # (event_type, path)

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix not in _WATCHED:
            return
        if any(part in _IGNORED for part in path.parts):
            return

        with self._lock:
            self._pending.append((event.event_type, str(path)))
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            events = list(self._pending)
            self._pending.clear()
            self._timer = None
        if events:
            # Pass the most recent event type for labelling
            self._on_change(events[-1][0], events[-1][1])


class ProjectWatcher:
    """
    High-level watcher: starts watchdog Observer and calls back into
    ProjectMind analyzers on each debounced batch of changes.
    """

    def __init__(
        self,
        project_path: str,
        debounce: float = 2.0,
        on_update: Callable[[str], None] | None = None,
    ):
        self.root = Path(project_path).resolve()
        self._debounce = debounce
        self._on_update = on_update or (lambda msg: None)
        self._observer: Observer | None = None
        self._run_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, block: bool = True) -> None:
        handler = _ChangeHandler(self._handle_change, self._debounce)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.root), recursive=True)
        self._observer.start()
        self._on_update(f"Watching {self.root}  (debounce {self._debounce}s)")
        if block:
            try:
                while self._observer.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_change(self, event_type: str, changed_path: str) -> None:
        self._run_count += 1
        rel = Path(changed_path).relative_to(self.root) if changed_path.startswith(str(self.root)) else Path(changed_path)
        self._on_update(f"[{self._run_count}] {event_type}: {rel}")
        self._refresh()

    def _refresh(self) -> None:
        try:
            self._run_dna()
        except Exception as e:
            self._on_update(f"  DNA error: {e}")

        try:
            self._run_graph()
        except Exception as e:
            self._on_update(f"  Graph error: {e}")

        try:
            self._run_health()
        except Exception as e:
            self._on_update(f"  Health error: {e}")

    def _run_dna(self) -> None:
        from backend.core.dna.extractor import DNAExtractor
        from backend.core.dna.generator import DNAGenerator
        t0 = time.monotonic()
        dna = DNAExtractor(str(self.root)).extract()
        DNAGenerator(dna).generate()
        elapsed = (time.monotonic() - t0) * 1000
        self._on_update(f"  DNA  refreshed  ({dna.source_files} files, {elapsed:.0f}ms)")

    def _run_graph(self) -> None:
        from backend.core.analyzer.ast_parser import ProjectParser
        from backend.core.graph.builder import GraphBuilder
        from backend.core.graph.serializer import GraphSerializer
        t0 = time.monotonic()
        analyses = ProjectParser(str(self.root)).parse()
        g = GraphBuilder(str(self.root)).build(analyses)
        out = self.root / ".projectmind" / "knowledge_graph" / "graph.json"
        GraphSerializer().save(g, out)
        elapsed = (time.monotonic() - t0) * 1000
        self._on_update(f"  Graph rebuilt   ({g.number_of_nodes()} nodes, {elapsed:.0f}ms)")

    def _run_health(self) -> None:
        from backend.core.analyzer.ast_parser import ProjectParser
        from backend.core.analyzer.dead_code import DeadCodeDetector
        from backend.core.analyzer.dependency import DependencyAnalyzer
        from backend.core.analyzer.duplicates import DuplicateDetector
        from backend.core.analyzer.reporter import Reporter
        from backend.core.analyzer.security import SecurityScanner
        t0 = time.monotonic()
        analyses = ProjectParser(str(self.root)).parse()
        ok = [a for a in analyses if not a.parse_error]
        dep = DependencyAnalyzer(str(self.root), analyses).analyze()
        dup = DuplicateDetector(analyses).detect()
        dead = DeadCodeDetector(analyses).detect()
        sec = SecurityScanner(str(self.root)).scan([a.path for a in ok])
        reporter = Reporter(str(self.root), "python", analyses, dep, dup, dead, sec)
        report = reporter.build()
        reporter.save(report)
        elapsed = (time.monotonic() - t0) * 1000
        self._on_update(
            f"  Health updated  ({report.health.overall}/10, {elapsed:.0f}ms)"
        )
