"""Deterministic column-usage classification via sqlglot (no LLM, no DataHub).

Binder P0 (multi-table resolve):
- Physical table count ignores CTE aliases (CTE names are not a second table)
- Optional ``subject_table`` (+ ``tables`` schema) binds hits to the subject only
- ``SELECT *`` over the subject (or any star when subject is unknown) → UNKNOWN
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from premortem.models import BreakSeverity

HARD_CLAUSES = frozenset(
    {
        "WHERE",
        "JOIN",
        "GROUP",
        "ORDER",
        "HAVING",
        "PARTITION",
        "QUALIFY",
    }
)


@dataclass
class ClassifyResult:
    severity: BreakSeverity
    evidence: str
    unknown_reason: str | None = None
    snippet: str = ""


def _clause_label(node: exp.Expression) -> str | None:
    cur: exp.Expression | None = node
    while cur is not None:
        if isinstance(cur, exp.Where):
            return "WHERE"
        if isinstance(cur, (exp.Join, exp.Pivot)):
            return "JOIN"
        if isinstance(cur, exp.Group):
            return "GROUP"
        if isinstance(cur, exp.Order):
            return "ORDER"
        if isinstance(cur, exp.Having):
            return "HAVING"
        if isinstance(cur, exp.Qualify):
            return "QUALIFY"
        if isinstance(cur, exp.Window) or (
            isinstance(cur, exp.PartitionBy) if hasattr(exp, "PartitionBy") else False
        ):
            return "PARTITION"
        if isinstance(cur, exp.Select):
            return "SELECT"
        cur = cur.parent
    return None


def _base_name(name: str | None) -> str:
    if not name:
        return ""
    return name.lower().split(".")[-1]


def _cte_sources(tree: exp.Expression) -> dict[str, set[str]]:
    """Map CTE alias → set of underlying physical base table names."""
    sources: dict[str, set[str]] = {}
    for cte in tree.find_all(exp.CTE):
        alias = _base_name(cte.alias_or_name)
        if not alias:
            continue
        physical: set[str] = set()
        body = cte.this
        if body is None:
            sources[alias] = physical
            continue
        for t in body.find_all(exp.Table):
            raw = _base_name(t.name)
            if not raw:
                continue
            if raw in sources:
                physical |= sources[raw]
            else:
                physical.add(raw)
        sources[alias] = physical
    return sources


def _alias_map(tree: exp.Expression, cte_sources: dict[str, set[str]]) -> dict[str, set[str]]:
    """Map table alias / name → physical base names in this query."""
    amap: dict[str, set[str]] = dict(cte_sources)
    for t in tree.find_all(exp.Table):
        raw = _base_name(t.name)
        if not raw:
            continue
        physical = cte_sources.get(raw, {raw})
        amap[_base_name(t.alias_or_name) or raw] = set(physical)
        amap[raw] = set(physical)
    return amap


def _physical_tables_in_scope(
    tree: exp.Expression, cte_sources: dict[str, set[str]]
) -> set[str]:
    physical: set[str] = set()
    for t in tree.find_all(exp.Table):
        raw = _base_name(t.name)
        if not raw:
            continue
        if raw in cte_sources:
            physical |= cte_sources[raw]
        else:
            physical.add(raw)
    return physical


def _enclosing_select(node: exp.Expression) -> exp.Select | None:
    cur: exp.Expression | None = node
    while cur is not None:
        if isinstance(cur, exp.Select):
            return cur
        cur = cur.parent
    return None


def _select_from_physical(
    select: exp.Select, cte_sources: dict[str, set[str]]
) -> set[str]:
    physical: set[str] = set()
    from_ = select.args.get("from_")
    if from_ is not None:
        for t in from_.find_all(exp.Table):
            raw = _base_name(t.name)
            if not raw:
                continue
            physical |= cte_sources.get(raw, {raw})
    for j in select.args.get("joins") or []:
        for t in j.find_all(exp.Table):
            raw = _base_name(t.name)
            if not raw:
                continue
            physical |= cte_sources.get(raw, {raw})
    return physical


def _is_projection_star(star: exp.Star) -> bool:
    """True for SELECT * / t.* — false for COUNT(*), SUM(*), etc."""
    parent = star.parent
    if parent is None:
        return True
    if isinstance(parent, exp.AggFunc):
        return False
    # Some dialects wrap aggregates differently
    if isinstance(parent, exp.Anonymous):
        return False
    return True


def _star_implies_unknown(
    tree: exp.Expression,
    *,
    subject: str | None,
    cte_sources: dict[str, set[str]],
) -> bool:
    """True when SELECT * may hide a subject-column reference."""
    stars = [s for s in tree.find_all(exp.Star) if _is_projection_star(s)]
    if not stars:
        return False
    if subject is None:
        return True
    for star in stars:
        sel = _enclosing_select(star)
        if sel is None:
            return True
        from_physical = _select_from_physical(sel, cte_sources)
        if not from_physical or subject in from_physical:
            return True
    return False


def _resolve_column_tables(
    node: exp.Column, alias_map: dict[str, set[str]], physical_in_scope: set[str]
) -> set[str] | None:
    """Return physical tables this column might bind to."""
    if node.table:
        key = _base_name(node.table)
        if key in alias_map:
            return set(alias_map[key])
        return {key}
    return set(physical_in_scope) if physical_in_scope else None


def classify_query(
    sql: str,
    *,
    column: str,
    dialect: str = "snowflake",
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> ClassifyResult:
    """Classify how `column` is used in `sql`.

    Rules:
    - HARD: subject-bound ref in JOIN/WHERE/GROUP/ORDER/HAVING/PARTITION
    - SOFT: subject-bound ref only in SELECT list
    - UNKNOWN: parse failure; SELECT *; bare col with ≥2 candidate tables
    - UNAFFECTED: no subject-bound reference (incl. cleared decoys)
    """
    col = column.lower()
    subject = _base_name(subject_table) if subject_table else None
    schema_by_base: dict[str, set[str]] = {}
    if tables:
        for tname, cols in tables.items():
            schema_by_base[_base_name(tname)] = {c.lower() for c in cols}

    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:  # noqa: BLE001 — surface as UNKNOWN
        return ClassifyResult(
            severity=BreakSeverity.UNKNOWN,
            evidence="PARSE",
            unknown_reason=f"sqlglot parse failed: {exc}",
            snippet=sql.strip()[:200],
        )

    cte_sources = _cte_sources(tree)
    alias_map = _alias_map(tree, cte_sources)
    physical_all = _physical_tables_in_scope(tree, cte_sources)

    bound: list[tuple[str, set[str] | None]] = []
    for node in tree.find_all(exp.Column):
        name = (node.name or "").lower()
        if name != col:
            continue
        clause = _clause_label(node) or "OTHER"
        sel = _enclosing_select(node)
        scope_physical = (
            _select_from_physical(sel, cte_sources) if sel is not None else physical_all
        )
        if not scope_physical:
            scope_physical = physical_all
        resolved = _resolve_column_tables(node, alias_map, scope_physical)

        if subject is None:
            if not node.table and len(scope_physical) > 1:
                return ClassifyResult(
                    severity=BreakSeverity.UNKNOWN,
                    evidence=clause,
                    unknown_reason=(
                        f"unqualified `{column}` with {len(scope_physical)} tables "
                        "in scope; needs human/agent"
                    ),
                    snippet=sql.strip()[:200],
                )
            bound.append((clause, resolved))
            continue

        if resolved is None:
            return ClassifyResult(
                severity=BreakSeverity.UNKNOWN,
                evidence=clause,
                unknown_reason=(
                    f"unqualified `{column}` could not be bound; needs human/agent"
                ),
                snippet=sql.strip()[:200],
            )

        if subject not in resolved:
            # Decoy / other-table reference — ignore
            continue

        if len(resolved) == 1:
            bound.append((clause, resolved))
            continue

        # Unqualified (or multi-candidate) including subject
        candidates = set(resolved)
        if schema_by_base:
            with_col = {
                t for t in candidates if t in schema_by_base and col in schema_by_base[t]
            }
            missing = {t for t in candidates if t not in schema_by_base}
            if missing:
                return ClassifyResult(
                    severity=BreakSeverity.UNKNOWN,
                    evidence=clause,
                    unknown_reason=(
                        "couldn't resolve table "
                        + ", ".join(sorted(missing))
                        + " — not guessing"
                    ),
                    snippet=sql.strip()[:200],
                )
            candidates = with_col
        if len(candidates) >= 2:
            return ClassifyResult(
                severity=BreakSeverity.UNKNOWN,
                evidence=clause,
                unknown_reason=(
                    f"unqualified `{column}` with {len(candidates)} tables in scope; "
                    "needs human/agent"
                ),
                snippet=sql.strip()[:200],
            )
        if subject in candidates:
            bound.append((clause, {subject}))

    # SELECT * hides refs only when there is no explicit subject-bound column hit.
    if not bound and _star_implies_unknown(
        tree, subject=subject, cte_sources=cte_sources
    ):
        return ClassifyResult(
            severity=BreakSeverity.UNKNOWN,
            evidence="STAR",
            unknown_reason="SELECT * may hide column references; needs schema expand or human",
            snippet=sql.strip()[:200],
        )

    if not bound:
        return ClassifyResult(
            severity=BreakSeverity.UNAFFECTED,
            evidence="NONE",
            snippet=sql.strip()[:200],
        )

    hard = [c for c, _ in bound if c in HARD_CLAUSES]
    if hard:
        return ClassifyResult(
            severity=BreakSeverity.HARD,
            evidence=",".join(sorted(set(hard))),
            snippet=sql.strip()[:200],
        )

    return ClassifyResult(
        severity=BreakSeverity.SOFT,
        evidence="SELECT",
        snippet=sql.strip()[:200],
    )
