"""Agent layer: adjudicate UNKNOWN findings (LLM-pluggable; heuristic default)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from premortem.classify import HARD_CLAUSES, classify_query
from premortem.models import BreakFinding, BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.rank import rank_findings


@dataclass
class Adjudication:
    severity: BreakSeverity
    note: str


class Adjudicator(Protocol):
    def adjudicate(
        self,
        *,
        finding: BreakFinding,
        sql: str,
        schema_fields: list[str],
        lineage_neighbors: list[str],
    ) -> Adjudication | None:
        """Return a HARD/SOFT ruling, or None to leave UNKNOWN."""


class HeuristicAdjudicator:
    """Deterministic binder for demo / offline — no API key.

    If the target column exists on the subject schema and the unknown hit
    was in a hard clause → HARD; if evidence is SELECT-only → SOFT.
    Otherwise leave UNKNOWN.
    """

    def adjudicate(
        self,
        *,
        finding: BreakFinding,
        sql: str,
        schema_fields: list[str],
        lineage_neighbors: list[str],
    ) -> Adjudication | None:
        fields = {f.lower() for f in schema_fields}
        if finding.column.lower() not in fields:
            return Adjudication(
                severity=BreakSeverity.UNKNOWN,
                note=(
                    f"column `{finding.column}` not in subject schema fields; "
                    "cannot bind — leave UNKNOWN"
                ),
            )

        clauses = {c.strip().upper() for c in finding.evidence.split(",") if c.strip()}
        if clauses & HARD_CLAUSES:
            return Adjudication(
                severity=BreakSeverity.HARD,
                note=(
                    f"bound `{finding.column}` to subject schema "
                    f"(fields include column; clause={finding.evidence}); "
                    "treat as HARD pending human confirm"
                ),
            )
        if "SELECT" in clauses:
            return Adjudication(
                severity=BreakSeverity.SOFT,
                note=(
                    f"bound `{finding.column}` to subject schema "
                    "(SELECT-only evidence); treat as SOFT pending human confirm"
                ),
            )
        return None


class CallableAdjudicator:
    """Wrap a function — used in unit tests to mock an LLM."""

    def __init__(
        self,
        fn: Callable[..., Adjudication | None],
    ) -> None:
        self._fn = fn

    def adjudicate(
        self,
        *,
        finding: BreakFinding,
        sql: str,
        schema_fields: list[str],
        lineage_neighbors: list[str],
    ) -> Adjudication | None:
        return self._fn(
            finding=finding,
            sql=sql,
            schema_fields=schema_fields,
            lineage_neighbors=lineage_neighbors,
        )


def adjudicate_forecast(
    forecast: Forecast,
    *,
    queries: list[QueryRecord],
    schema_fields: list[str],
    lineage_neighbors: list[str] | None = None,
    adjudicator: Adjudicator | None = None,
    use_exec_count: bool = False,
) -> Forecast:
    """Upgrade UNKNOWN findings via adjudicator; leave others unchanged."""
    adj = adjudicator or HeuristicAdjudicator()
    neighbors = lineage_neighbors or []
    by_id = {q.query_id: q for q in queries}
    updated: list[BreakFinding] = []
    for f in forecast.findings:
        if f.severity is not BreakSeverity.UNKNOWN:
            updated.append(f)
            continue
        sql = by_id[f.query_id].sql if f.query_id in by_id else f.sql_snippet
        result = adj.adjudicate(
            finding=f,
            sql=sql,
            schema_fields=schema_fields,
            lineage_neighbors=neighbors,
        )
        if result is None or result.severity is BreakSeverity.UNKNOWN:
            note = result.note if result else None
            updated.append(
                f.model_copy(update={"agent_note": note or f.agent_note})
            )
            continue
        if result.severity not in (BreakSeverity.HARD, BreakSeverity.SOFT):
            updated.append(f)
            continue
        updated.append(
            f.model_copy(
                update={
                    "severity": result.severity,
                    "agent_note": result.note,
                    "unknown_reason": None,
                }
            )
        )
    ranked = rank_findings(updated, use_exec_count=use_exec_count)
    return forecast.model_copy(update={"findings": ranked})


def rehearse(
    *,
    diff: SchemaDiff,
    queries: list[QueryRecord],
    lineage_dependent_count: int = 0,
    dialect: str = "snowflake",
    use_exec_count: bool = False,
    schema_fields: list[str] | None = None,
    lineage_neighbors: list[str] | None = None,
    adjudicate: bool = False,
    adjudicator: Adjudicator | None = None,
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> Forecast:
    """Classify → optional adjudicate → Forecast."""
    from premortem.forecast import build_forecast

    forecast = build_forecast(
        diff=diff,
        queries=queries,
        lineage_dependent_count=lineage_dependent_count,
        dialect=dialect,
        use_exec_count=use_exec_count,
        subject_table=subject_table,
        tables=tables,
    )
    if not adjudicate:
        return forecast
    fields = schema_fields
    if fields is None:
        # Offline: assume column under change exists on subject.
        fields = [diff.column]
    return adjudicate_forecast(
        forecast,
        queries=queries,
        schema_fields=fields,
        lineage_neighbors=lineage_neighbors or [],
        adjudicator=adjudicator,
        use_exec_count=use_exec_count,
    )
