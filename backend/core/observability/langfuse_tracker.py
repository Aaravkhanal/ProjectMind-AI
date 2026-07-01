"""
Langfuse + OpenTelemetry observability integration.

Tracks:
  - LLM calls: model, tokens, cost, latency
  - Agent traces: which agents ran, in which order
  - Errors and retries

Activation: set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY in .env.local
Falls back to a no-op if not configured.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional


def _langfuse_client():
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not (pk and sk):
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(public_key=pk, secret_key=sk, host=host)
    except ImportError:
        return None


class Tracer:
    """
    Lightweight wrapper around Langfuse for agent + LLM tracing.

    Usage:
        tracer = Tracer(project_path=".", operation="review")
        with tracer.span("architect_agent", model="claude-sonnet"):
            result = run_architect(...)
            tracer.record(tokens_in=500, tokens_out=300, cost=0.002)
    """

    def __init__(self, project_path: str = ".", operation: str = "review"):
        self.project_path = project_path
        self.operation    = operation
        self._client      = _langfuse_client()
        self._trace       = None
        self._current_span = None
        self._start_time  = time.time()

        if self._client:
            try:
                self._trace = self._client.trace(
                    name=f"projectmind/{operation}",
                    metadata={"project_path": project_path},
                )
            except Exception:
                self._trace = None

    @contextmanager
    def span(
        self,
        name: str,
        model: Optional[str] = None,
        input_text: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        span = None
        t0 = time.time()
        if self._trace:
            try:
                span = self._trace.span(
                    name=name,
                    input={"text": input_text[:500] if input_text else ""},
                    metadata={"model": model, **(metadata or {})},
                )
                self._current_span = span
            except Exception:
                pass

        try:
            yield self
        finally:
            latency_ms = (time.time() - t0) * 1000
            if span:
                try:
                    span.end(metadata={"latency_ms": latency_ms})
                except Exception:
                    pass
            self._current_span = None

    def record(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        model: Optional[str] = None,
        output_text: Optional[str] = None,
    ) -> None:
        if not self._current_span:
            return
        try:
            self._current_span.update(
                output={"text": (output_text or "")[:300]},
                usage={"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out},
                metadata={"cost_usd": cost_usd, "model": model},
            )
        except Exception:
            pass

    def error(self, message: str) -> None:
        if self._current_span:
            try:
                self._current_span.update(level="ERROR", status_message=message)
            except Exception:
                pass

    def finish(self) -> None:
        if self._trace:
            try:
                self._trace.update(
                    metadata={"total_duration_ms": (time.time() - self._start_time) * 1000}
                )
                self._client.flush()
            except Exception:
                pass


def noop_tracer(project_path: str = ".", operation: str = "review") -> Tracer:
    """Returns a Tracer that silently does nothing (when Langfuse is unconfigured)."""
    return Tracer(project_path, operation)


def traced(operation: str):
    """
    Decorator to automatically trace a function with Langfuse.

    @traced("review")
    def run_review(diff, project_path, ...):
        ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            project_path = kwargs.get("project_path", ".")
            tracer = Tracer(project_path=project_path, operation=operation)
            try:
                result = fn(*args, **kwargs)
                tracer.finish()
                return result
            except Exception as e:
                tracer.error(str(e))
                tracer.finish()
                raise
        return wrapper
    return decorator
