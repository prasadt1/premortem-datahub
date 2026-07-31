"""Build a Forecast from normalized QueryRecords (no DataHub / no LLM)."""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.models import BreakFinding, BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.rank import rank_findings

CLEARED_PREFIX = "BOUND_ELSEWHERE:"


def is_cleared_finding(evidence: str) -> bool:
    """True when UNAFFECTED because the column binds to a non-subject table."""
    return evidence.startswith(CLEARED_PREFIX)


def cleared_bind_table(evidence: str) -> str | None:
    if not is_cleared_finding(evidence):
        return None
    return evidence[len(CLEARED_PREFIX) :] or None


def build_forecast(
    *,
    diff: SchemaDiff,
    queries: list[QueryRecord],
    lineage_dependent_count: int = 0,
    dialect: str = "snowflake",
    use_exec_count: bool = False,
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> Forecast:
    """Classify each query against ``diff.column`` and assemble a Forecast.

    CLEARED decoys (UNAFFECTED + BOUND_ELSEWHERE) are emitted as findings so
    the report can show false-alarm suppression. Pure NO_REFERENCE rows stay
    as ``unaffected_lineage_count`` (no query evidence of the column).
    """
    findings: list[BreakFinding] = []
    no_reference = 0
    for q in queries:
        result = classify_query(
            q.sql,
            column=diff.column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables,
        )
        if (
            result.severity is BreakSeverity.UNAFFECTED
            and not is_cleared_finding(result.evidence)
        ):
            no_reference += 1
            continue
        findings.append(
            BreakFinding(
                query_id=q.query_id,
                sql_snippet=result.snippet or q.sql.strip()[:200],
                severity=result.severity,
                column=diff.column,
                evidence=result.evidence,
                exec_count=q.exec_count,
                unknown_reason=result.unknown_reason,
                unknown_kind=result.unknown_kind,
            )
        )
    ranked = rank_findings(findings, use_exec_count=use_exec_count)
    return Forecast(
        diff=diff,
        lineage_dependent_count=lineage_dependent_count,
        findings=ranked,
        unaffected_lineage_count=no_reference,
    )
