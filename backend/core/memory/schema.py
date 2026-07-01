from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    name: str
    description: str
    files_changed: str = Field(default="[]")   # JSON array of file paths
    patterns: str = Field(default="[]")         # JSON array of pattern names
    status: str = Field(default="pending")       # pending | success | failure
    outcome_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ErrorMemory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    error: str
    fix: str
    confidence: float = Field(default=0.5)
    occurrences: int = Field(default=1)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Decision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    decision: str
    reason: str
    outcome: Optional[str] = None
    confidence: float = Field(default=0.8)
    superseded_by: Optional[int] = Field(default=None, foreign_key="decision.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Pattern(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_path: str = Field(index=True)
    name: str
    description: str
    category: str   # coding_style | design_pattern | naming | structure
    example: Optional[str] = None
    confidence: float = Field(default=0.5)
    occurrence_count: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
