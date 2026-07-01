import platform
from datetime import datetime, timezone

from fastapi import APIRouter

from backend.version import __version__

router = APIRouter(tags=["health"])

_start_time = datetime.now(timezone.utc)


@router.get("/health")
def health():
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return {
        "status": "ok",
        "service": "ProjectMind AI",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "uptime_seconds": round(uptime, 1),
        "python": platform.python_version(),
    }


@router.get("/")
def root():
    return {
        "service": "ProjectMind AI",
        "version": __version__,
        "description": "The persistent memory layer for AI coding agents",
        "docs": "/docs",
        "health": "/health",
    }
