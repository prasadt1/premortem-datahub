from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BreakSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    UNKNOWN = "unknown"
    UNAFFECTED = "unaffected"


class SchemaDiff(BaseModel):
    dataset_urn: str
    kind: str  # rename | drop
    column: str
    new_column: str | None = None


class QueryRecord(BaseModel):
    """Normalized query row — exec_count only when live API returns it."""

    query_id: str
    sql: str
    dataset_urn: str | None = None
    exec_count: int | None = None


class BreakFinding(BaseModel):
    query_id: str
    sql_snippet: str
    severity: BreakSeverity
    column: str
    evidence: str
    exec_count: int | None = None
    agent_note: str | None = None
    unknown_reason: str | None = None


class Forecast(BaseModel):
    diff: SchemaDiff
    lineage_dependent_count: int = 0
    findings: list[BreakFinding] = Field(default_factory=list)
    unaffected_lineage_count: int = 0
