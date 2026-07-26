from __future__ import annotations

import json

from premortem.models import BreakSeverity, Forecast
from premortem.rank import rank_findings


def to_markdown(forecast: Forecast, *, use_exec_count: bool) -> str:
    ranked = rank_findings(forecast.findings, use_exec_count=use_exec_count)
    d = forecast.diff
    change = (
        f"{d.column} → rename to {d.new_column}"
        if d.kind == "rename"
        else f"drop {d.column}"
    )
    lines = [
        f"Schema rehearsal: {change}",
        "",
        f"Impact Analysis baseline: {forecast.lineage_dependent_count} downstream dependents",
        "",
    ]
    for sev in (BreakSeverity.HARD, BreakSeverity.SOFT, BreakSeverity.UNKNOWN):
        group = [f for f in ranked if f.severity is sev]
        label = {
            BreakSeverity.HARD: "HARD",
            BreakSeverity.SOFT: "SOFT",
            BreakSeverity.UNKNOWN: "UNKNOWN / needs human",
        }[sev]
        lines.append(f"{label} ({len(group)})")
        if not group:
            lines.append("- (none)")
        for f in group:
            extra = ""
            if use_exec_count and f.exec_count is not None:
                extra = f"  (exec×{f.exec_count})"
            reason = f" — {f.unknown_reason}" if f.unknown_reason else ""
            note = f" — agent: {f.agent_note}" if f.agent_note else ""
            lines.append(
                f"- {f.query_id} — [{f.evidence}] {f.sql_snippet[:120]}{extra}{reason}{note}"
            )
        lines.append("")
    lines.append(
        f"UNAFFECTED / no query evidence: {forecast.unaffected_lineage_count}"
    )
    return "\n".join(lines).rstrip() + "\n"


def to_json(forecast: Forecast, *, use_exec_count: bool) -> str:
    ranked = rank_findings(forecast.findings, use_exec_count=use_exec_count)
    payload = forecast.model_copy(update={"findings": ranked})
    return payload.model_dump_json(indent=2)
