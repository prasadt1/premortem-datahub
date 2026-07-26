from __future__ import annotations

from premortem.models import BreakFinding, BreakSeverity

_ORDER = {
    BreakSeverity.HARD: 0,
    BreakSeverity.SOFT: 1,
    BreakSeverity.UNKNOWN: 2,
    BreakSeverity.UNAFFECTED: 3,
}


def rank_findings(
    findings: list[BreakFinding],
    *,
    use_exec_count: bool,
) -> list[BreakFinding]:
    """HARD → SOFT → UNKNOWN → UNAFFECTED; optional exec_count within tier."""

    def key(f: BreakFinding) -> tuple:
        tier = _ORDER.get(f.severity, 9)
        if use_exec_count and f.exec_count is not None:
            return (tier, -f.exec_count, f.query_id)
        return (tier, f.query_id)

    return sorted(findings, key=key)
