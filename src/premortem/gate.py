"""Merge gate — CI exit code over a Premortem forecast.

``premortem gate --rename old:new [--fail-on hard|hard,unknown|…]``
Exit 0 when no finding meets the fail threshold; non-zero otherwise.
JSON summary always on stdout.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from premortem.agent import rehearse
from premortem.catalog import CatalogClient
from premortem.live import run_live_rehearsal
from premortem.forecast import is_cleared_finding
from premortem.models import BreakSeverity, Forecast, QueryRecord, SchemaDiff

_SEVERITY_RANK = {
    BreakSeverity.HARD: 3,
    BreakSeverity.SOFT: 2,
    BreakSeverity.UNKNOWN: 1,
    BreakSeverity.UNAFFECTED: 0,
}


def parse_fail_on(spec: str) -> frozenset[BreakSeverity]:
    """Parse ``hard``, ``hard,unknown``, ``hard,soft,unknown`` → severity set."""
    parts = [p.strip().lower() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ValueError("--fail-on must name at least one severity")
    out: set[BreakSeverity] = set()
    for p in parts:
        try:
            sev = BreakSeverity(p)
        except ValueError as exc:
            raise ValueError(
                f"unknown severity in --fail-on: {p!r} "
                "(use hard, soft, unknown)"
            ) from exc
        if sev is BreakSeverity.UNAFFECTED:
            raise ValueError("UNAFFECTED is not a fail threshold")
        out.add(sev)
    return frozenset(out)


@dataclass
class GateSummary:
    clean: bool
    fail_on: list[str]
    triggered: list[str]
    counts: dict[str, int]
    findings: list[dict]
    exit_code: int
    unparseable: int = 0
    note: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def evaluate_gate(
    forecast: Forecast,
    *,
    fail_on: frozenset[BreakSeverity],
) -> GateSummary:
    counts = {
        "hard": 0,
        "soft": 0,
        "unknown": 0,
        "unaffected": 0,
        "cleared": 0,
    }
    triggered: list[str] = []
    findings_out: list[dict] = []
    unparseable = 0
    for f in forecast.findings:
        key = f.severity.value
        counts[key] = counts.get(key, 0) + 1
        if f.severity is BreakSeverity.UNAFFECTED and is_cleared_finding(f.evidence):
            counts["cleared"] = counts.get("cleared", 0) + 1
        if f.severity is BreakSeverity.UNKNOWN and (
            f.evidence == "PARSE" or f.unknown_kind == "parse"
        ):
            unparseable += 1
        row = {
            "query_id": f.query_id,
            "severity": f.severity.value,
            "evidence": f.evidence,
        }
        findings_out.append(row)
        if f.severity in fail_on:
            triggered.append(f.query_id)

    clean = len(triggered) == 0
    exit_code = 0 if clean else 1
    note = None
    # Unparseable input must not silently pass when UNKNOWN is not a fail threshold
    if (
        unparseable
        and BreakSeverity.UNKNOWN not in fail_on
        and clean
    ):
        clean = False
        exit_code = 2
        note = (
            f"{unparseable} queries could not be parsed — refusing silent green. "
            "Include unknown in --fail-on (default) or fix the SQL."
        )
    elif unparseable and BreakSeverity.UNKNOWN not in fail_on:
        note = (
            f"{unparseable} queries could not be parsed "
            "(not in --fail-on; exit already non-zero on other findings)"
        )

    return GateSummary(
        clean=clean,
        fail_on=sorted(s.value for s in fail_on),
        triggered=triggered,
        counts=counts,
        findings=findings_out,
        exit_code=exit_code,
        unparseable=unparseable,
        note=note,
    )


def run_offline_gate(
    *,
    diff: SchemaDiff,
    queries: list[QueryRecord],
    fail_on: frozenset[BreakSeverity],
    dialect: str = "snowflake",
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> GateSummary:
    forecast = rehearse(
        diff=diff,
        queries=queries,
        lineage_dependent_count=0,
        dialect=dialect,
        adjudicate=False,
        subject_table=subject_table,
        tables=tables,
    )
    return evaluate_gate(forecast, fail_on=fail_on)


def run_live_gate(
    client: CatalogClient,
    *,
    diff: SchemaDiff,
    fail_on: frozenset[BreakSeverity],
    dialect: str = "snowflake",
) -> GateSummary:
    result = run_live_rehearsal(
        client,
        diff=diff,
        dialect=dialect,
        adjudicate=False,
        write_back=False,
    )
    return evaluate_gate(result.forecast, fail_on=fail_on)


def worst_severity(forecast: Forecast) -> BreakSeverity | None:
    worst: BreakSeverity | None = None
    for f in forecast.findings:
        if f.severity is BreakSeverity.UNAFFECTED:
            continue
        if worst is None or _SEVERITY_RANK[f.severity] > _SEVERITY_RANK[worst]:
            worst = f.severity
    return worst
