"""Query-history helpers shared by catalog backends."""

from __future__ import annotations

from premortem.models import QueryRecord


def normalize_sql(sql: str) -> str:
    """Collapse whitespace / case so repeated log statements share one key."""
    return " ".join(sql.split()).lower()


def dedupe_queries_by_sql(records: list[QueryRecord]) -> list[QueryRecord]:
    """Keep first occurrence of each normalized SQL (real logs genuinely repeat)."""
    seen: set[str] = set()
    out: list[QueryRecord] = []
    for q in records:
        key = normalize_sql(q.sql)
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def filter_self_urn(urn: str, related: list[str]) -> list[str]:
    """Drop the subject URN from a lineage neighbor list (self-edges are not dependents)."""
    return [u for u in related if u != urn]
