"""Resolve SQL sibling tables to catalog schemas for multi-table binding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from premortem.catalog.protocol import CatalogClient
from premortem.classify import _base_name, _cte_sources, _physical_tables_in_scope


def extract_physical_table_names(sql: str, *, dialect: str = "snowflake") -> set[str]:
    """Return physical base table names referenced in ``sql`` (CTEs expanded away)."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return set()
    cte_sources = _cte_sources(tree)
    return _physical_tables_in_scope(tree, cte_sources)


def _urn_parts(urn: str) -> tuple[str | None, str | None, str | None]:
    """Return (platform, name, env) from a dataset URN, or Nones."""
    # urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91....order_history,PROD)
    m = re.match(
        r"urn:li:dataset:\(urn:li:dataPlatform:([^,]+),([^,]+),([^)]+)\)",
        urn,
    )
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)


def pick_best_urn(table: str, candidates: list[str], *, subject_urn: str) -> str | None:
    """Prefer same platform + shared name path as the subject dataset."""
    want = _base_name(table)
    if not want:
        return None
    subj_platform, subj_name, _ = _urn_parts(subject_urn)
    scored: list[tuple[int, str]] = []
    for urn in candidates:
        platform, name, _ = _urn_parts(urn)
        if not name or _base_name(name) != want:
            continue
        score = 0
        if platform and subj_platform and platform.lower() == subj_platform.lower():
            score += 10
        if subj_name and name.lower().startswith(subj_name.rsplit(".", 1)[0].lower()):
            # same db/schema prefix when possible
            score += 5
        if "." in name and want in name.lower().split("."):
            score += 1
        scored.append((score, urn))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


@dataclass
class SiblingSchemaResolution:
    """Merged table→columns map for a rehearsal run."""

    tables: dict[str, list[str]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    urn_by_table: dict[str, str] = field(default_factory=dict)


def resolve_sibling_schemas(
    client: CatalogClient,
    *,
    subject_urn: str,
    subject_table: str,
    subject_fields: list[str],
    sql_statements: list[str],
    dialect: str = "snowflake",
    cache: dict[str, str | None] | None = None,
) -> SiblingSchemaResolution:
    """Walk SQL → catalog search → schema fields; cache URN picks per table name."""
    urn_cache: dict[str, str | None] = cache if cache is not None else {}
    names: set[str] = set()
    for sql in sql_statements:
        names |= extract_physical_table_names(sql, dialect=dialect)

    result = SiblingSchemaResolution()
    subject_base = _base_name(subject_table)
    result.tables[subject_base] = list(subject_fields)
    result.urn_by_table[subject_base] = subject_urn

    for raw in sorted(names):
        base = _base_name(raw)
        if not base or base == subject_base:
            continue
        if base in urn_cache:
            urn = urn_cache[base]
        else:
            hits = client.search_datasets(base, limit=20)
            urn = pick_best_urn(base, hits, subject_urn=subject_urn)
            urn_cache[base] = urn
        if not urn:
            result.unresolved.append(base)
            continue
        fields = client.list_schema_fields(urn)
        if not fields:
            result.unresolved.append(base)
            continue
        bare = sorted({f.split(".")[-1] for f in fields})
        result.tables[base] = bare
        result.urn_by_table[base] = urn

    result.unresolved = sorted(set(result.unresolved))
    return result
