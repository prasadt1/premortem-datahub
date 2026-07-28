"""Build a Forecast from normalized QueryRecords (no DataHub / no LLM)."""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.models import BreakFinding, BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.rank import rank_findings


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
    """Classify each query against ``diff.column`` and assemble a Forecast."""
    findings: list[BreakFinding] = []
    unaffected = 0
    for q in queries:
        result = classify_query(
            q.sql,
            column=diff.column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables,
        )
        if result.severity is BreakSeverity.UNAFFECTED:
            unaffected += 1
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
            )
        )
    ranked = rank_findings(findings, use_exec_count=use_exec_count)
    return Forecast(
        diff=diff,
        lineage_dependent_count=lineage_dependent_count,
        findings=ranked,
        unaffected_lineage_count=unaffected,
    )
