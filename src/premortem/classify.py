"""Deterministic column-usage classification via sqlglot (no LLM, no DataHub).

Binder P0 (multi-table resolve):
- Physical table count ignores CTE aliases (CTE names are not a second table)
- Optional ``subject_table`` (+ ``tables`` schema) binds hits to the subject only
- ``SELECT *`` over the subject (or any star when subject is unknown) → UNKNOWN

``analyze_bindings`` is the shared seam: classify collapses it to a verdict;
rewrite renames only the subject-bound column nodes it returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class BindingAnalysis:
    """Full binding decision for one query — classify and rewrite both consume this."""

    severity: BreakSeverity
    evidence: str
    unknown_reason: str | None = None
    snippet: str = ""
    tree: exp.Expression | None = None
    subject_bound_nodes: list[exp.Column] = field(default_factory=list)
    elsewhere: frozenset[str] = frozenset()
    dialect: str = "snowflake"

    def to_classify_result(self) -> ClassifyResult:
        return ClassifyResult(
            severity=self.severity,
            evidence=self.evidence,
            unknown_reason=self.unknown_reason,
            snippet=self.snippet,
        )


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


def _unnest_aliases(tree: exp.Expression) -> set[str]:
    """Aliases introduced by UNNEST(... ) AS x — not physical tables."""
    out: set[str] = set()
    for u in tree.find_all(exp.Unnest):
        alias = u.args.get("alias")
        if alias is None:
            continue
        for col_id in alias.args.get("columns") or []:
            name = getattr(col_id, "name", None)
            if name is None and hasattr(col_id, "this"):
                inner = col_id.this
                name = getattr(inner, "name", None) or getattr(inner, "this", None)
            if name:
                out.add(_base_name(str(name)))
        an = getattr(alias, "name", None)
        if an:
            out.add(_base_name(str(an)))
    return out


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


def _unknown(
    *,
    evidence: str,
    reason: str,
    snippet: str,
    dialect: str,
    tree: exp.Expression | None = None,
) -> BindingAnalysis:
    return BindingAnalysis(
        severity=BreakSeverity.UNKNOWN,
        evidence=evidence,
        unknown_reason=reason,
        snippet=snippet,
        tree=tree,
        dialect=dialect,
    )


def analyze_bindings(
    sql: str,
    *,
    column: str,
    dialect: str = "snowflake",
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> BindingAnalysis:
    """Resolve every matching column ref; collapse to a verdict + subject-bound nodes."""
    col = column.lower()
    subject = _base_name(subject_table) if subject_table else None
    schema_by_base: dict[str, set[str]] = {}
    if tables:
        for tname, cols in tables.items():
            schema_by_base[_base_name(tname)] = {c.lower() for c in cols}
    snippet = sql.strip()[:200]

    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:  # noqa: BLE001 — surface as UNKNOWN
        return _unknown(
            evidence="PARSE",
            reason=f"sqlglot parse failed: {exc}",
            snippet=snippet,
            dialect=dialect,
        )

    cte_sources = _cte_sources(tree)
    alias_map = _alias_map(tree, cte_sources)
    physical_all = _physical_tables_in_scope(tree, cte_sources)
    unnest_aliases = _unnest_aliases(tree)

    bound: list[tuple[str, exp.Column]] = []
    elsewhere: set[str] = set()
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
                return _unknown(
                    evidence=clause,
                    reason=(
                        f"unqualified `{column}` with {len(scope_physical)} tables "
                        "in scope; needs human/agent"
                    ),
                    snippet=snippet,
                    dialect=dialect,
                    tree=tree,
                )
            bound.append((clause, node))
            continue

        if resolved is None:
            return _unknown(
                evidence=clause,
                reason=(
                    f"unqualified `{column}` could not be bound; needs human/agent"
                ),
                snippet=snippet,
                dialect=dialect,
                tree=tree,
            )

        if subject not in resolved:
            known_elsewhere = {
                t
                for t in resolved
                if t and t in schema_by_base and t != subject
            }
            unknown_quals = {
                t for t in resolved if t and t not in schema_by_base
            }
            if unknown_quals:
                for t in sorted(unknown_quals):
                    if t in unnest_aliases:
                        return _unknown(
                            evidence=clause,
                            reason=(
                                f"couldn't resolve qualifier `{t}` — not guessing"
                            ),
                            snippet=snippet,
                            dialect=dialect,
                            tree=tree,
                        )
                    if t in alias_map or t in physical_all:
                        return _unknown(
                            evidence=clause,
                            reason=(
                                f"couldn't resolve qualifier `{t}` — not guessing"
                            ),
                            snippet=snippet,
                            dialect=dialect,
                            tree=tree,
                        )
                    if subject not in scope_physical:
                        return _unknown(
                            evidence=clause,
                            reason=(
                                f"couldn't resolve qualifier `{t}` — not guessing"
                            ),
                            snippet=snippet,
                            dialect=dialect,
                            tree=tree,
                        )
                bound.append((clause, node))
                continue
            if known_elsewhere:
                elsewhere |= known_elsewhere
            continue

        if len(resolved) == 1:
            bound.append((clause, node))
            continue

        candidates = set(resolved)
        if schema_by_base:
            with_col = {
                t for t in candidates if t in schema_by_base and col in schema_by_base[t]
            }
            missing = {t for t in candidates if t not in schema_by_base}
            if missing:
                return _unknown(
                    evidence=clause,
                    reason=(
                        "couldn't resolve table "
                        + ", ".join(sorted(missing))
                        + " — not guessing"
                    ),
                    snippet=snippet,
                    dialect=dialect,
                    tree=tree,
                )
            candidates = with_col
        if len(candidates) >= 2:
            return _unknown(
                evidence=clause,
                reason=(
                    f"unqualified `{column}` with {len(candidates)} tables in scope; "
                    "needs human/agent"
                ),
                snippet=snippet,
                dialect=dialect,
                tree=tree,
            )
        if subject in candidates:
            bound.append((clause, node))

    if not bound and _star_implies_unknown(
        tree, subject=subject, cte_sources=cte_sources
    ):
        return _unknown(
            evidence="STAR",
            reason="SELECT * may hide column references; needs schema expand or human",
            snippet=snippet,
            dialect=dialect,
            tree=tree,
        )

    subject_nodes = [n for _, n in bound]
    elsewhere_fs = frozenset(elsewhere)

    if not bound:
        if elsewhere:
            bound_to = ",".join(sorted(elsewhere))
            return BindingAnalysis(
                severity=BreakSeverity.UNAFFECTED,
                evidence=f"BOUND_ELSEWHERE:{bound_to}",
                snippet=snippet,
                tree=tree,
                elsewhere=elsewhere_fs,
                dialect=dialect,
            )
        return BindingAnalysis(
            severity=BreakSeverity.UNAFFECTED,
            evidence="NO_REFERENCE",
            snippet=snippet,
            tree=tree,
            elsewhere=elsewhere_fs,
            dialect=dialect,
        )

    hard = [c for c, _ in bound if c in HARD_CLAUSES]
    if hard:
        return BindingAnalysis(
            severity=BreakSeverity.HARD,
            evidence=",".join(sorted(set(hard))),
            snippet=snippet,
            tree=tree,
            subject_bound_nodes=subject_nodes,
            elsewhere=elsewhere_fs,
            dialect=dialect,
        )

    return BindingAnalysis(
        severity=BreakSeverity.SOFT,
        evidence="SELECT",
        snippet=snippet,
        tree=tree,
        subject_bound_nodes=subject_nodes,
        elsewhere=elsewhere_fs,
        dialect=dialect,
    )


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
    - UNAFFECTED: no subject-bound reference (incl. CLEARED decoys that positively
      resolve to a *known* non-subject table in ``tables``)
    """
    return analyze_bindings(
        sql,
        column=column,
        dialect=dialect,
        subject_table=subject_table,
        tables=tables,
    ).to_classify_result()
