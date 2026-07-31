"""Who-to-warn — owners of the subject and downstream assets, ranked by severity.

Reads ``get_owners`` from the catalog. Missing ownership is an honest output
("no owners recorded in DataHub"), not a failure.
"""

from __future__ import annotations

from dataclasses import dataclass

from premortem.catalog import CatalogClient
from premortem.models import BreakSeverity, Forecast

_SEVERITY_ORDER = (
    BreakSeverity.HARD,
    BreakSeverity.SOFT,
    BreakSeverity.UNKNOWN,
)


def owner_label(urn: str) -> str:
    """Bare name for camera; URN secondary in backticks."""
    bare = urn.rsplit(":", 1)[-1] if ":" in urn else urn
    return f"{bare} (`{urn}`)"


@dataclass(frozen=True)
class NotifyTarget:
    urn: str
    role: str  # subject | downstream
    owners: tuple[str, ...]
    worst_severity: BreakSeverity | None  # None → no breaking findings


def _worst_across(forecast: Forecast) -> BreakSeverity | None:
    rank = {
        BreakSeverity.HARD: 3,
        BreakSeverity.SOFT: 2,
        BreakSeverity.UNKNOWN: 1,
    }
    worst: BreakSeverity | None = None
    for f in forecast.findings:
        if f.severity not in rank:
            continue
        if worst is None or rank[f.severity] > rank[worst]:
            worst = f.severity
    return worst


def build_notify(
    client: CatalogClient,
    *,
    subject_urn: str,
    downstream: list[str],
    forecast: Forecast,
) -> list[NotifyTarget]:
    """Owners of subject + each downstream, tagged with the forecast's worst severity.

    Findings are query-scoped (not per-downstream), so every dependent shares the
    rehearsal's worst breaking severity — coordination signal, not a false claim
    that each URN was proven broken.
    """
    worst = _worst_across(forecast)
    targets: list[NotifyTarget] = []
    seen: set[str] = set()

    def _add(urn: str, role: str) -> None:
        if urn in seen:
            return
        seen.add(urn)
        owners = tuple(client.get_owners(urn))
        targets.append(
            NotifyTarget(
                urn=urn,
                role=role,
                owners=owners,
                worst_severity=worst if role == "subject" or worst else worst,
            )
        )

    _add(subject_urn, "subject")
    for d in downstream:
        _add(d, "downstream")
    return targets


def notify_markdown(targets: list[NotifyTarget]) -> str:
    """Render the Notify section body (no leading heading — caller adds it)."""
    if not targets:
        return "- (none)\n"

    lines: list[str] = []
    any_owners = any(t.owners for t in targets)
    if not any_owners:
        lines.append(
            "- no owners recorded in DataHub — coordination list empty "
            "(record Ownership aspects to populate this section)"
        )
        for t in targets:
            sev = t.worst_severity.value if t.worst_severity else "n/a"
            lines.append(f"- `{t.urn}` ({t.role}, worst={sev})")
        return "\n".join(lines) + "\n"

    # Group by worst severity for the ones that have owners; list unowned separately.
    by_sev: dict[str, list[NotifyTarget]] = {}
    unowned: list[NotifyTarget] = []
    for t in targets:
        if not t.owners:
            unowned.append(t)
            continue
        key = t.worst_severity.value if t.worst_severity else "unaffected"
        by_sev.setdefault(key, []).append(t)

    for sev in ("hard", "soft", "unknown", "unaffected"):
        group = by_sev.get(sev) or []
        if not group:
            continue
        lines.append(f"{sev.upper()} priority")
        for t in group:
            owners = ", ".join(owner_label(o) for o in t.owners)
            lines.append(f"- `{t.urn}` ({t.role}) → {owners}")
        lines.append("")

    if unowned:
        lines.append("no owners recorded")
        for t in unowned:
            sev = t.worst_severity.value if t.worst_severity else "n/a"
            lines.append(f"- `{t.urn}` ({t.role}, worst={sev})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
