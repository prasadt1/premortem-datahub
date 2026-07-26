"""Deterministic column-usage classification via sqlglot (no LLM, no DataHub)."""

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


def _table_count(tree: exp.Expression) -> int:
    tables = {t.alias_or_name for t in tree.find_all(exp.Table) if t.name}
    return len(tables)


def classify_query(
    sql: str,
    *,
    column: str,
    dialect: str = "snowflake",
) -> ClassifyResult:
    """Classify how `column` is used in `sql`.

    Rules:
    - HARD: referenced in JOIN/WHERE/GROUP/ORDER/HAVING/PARTITION
    - SOFT: referenced only in SELECT list
    - UNKNOWN: parse failure, or unqualified hit with >1 table in scope
    - UNAFFECTED: no reference to column name
    """
    col = column.lower()
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:  # noqa: BLE001 — surface as UNKNOWN
        return ClassifyResult(
            severity=BreakSeverity.UNKNOWN,
            evidence="PARSE",
            unknown_reason=f"sqlglot parse failed: {exc}",
            snippet=sql.strip()[:200],
        )

    hits: list[tuple[str, bool, exp.Column]] = []
    for node in tree.find_all(exp.Column):
        name = (node.name or "").lower()
        if name != col:
            continue
        qualified = bool(node.table)
        clause = _clause_label(node) or "OTHER"
        hits.append((clause, qualified, node))

    if not hits:
        return ClassifyResult(
            severity=BreakSeverity.UNAFFECTED,
            evidence="NONE",
            snippet=sql.strip()[:200],
        )

    n_tables = _table_count(tree)
    for clause, qualified, _node in hits:
        if not qualified and n_tables > 1:
            return ClassifyResult(
                severity=BreakSeverity.UNKNOWN,
                evidence=clause,
                unknown_reason=(
                    f"unqualified `{column}` with {n_tables} tables in scope; needs human/agent"
                ),
                snippet=sql.strip()[:200],
            )

    hard = [c for c, _, _ in hits if c in HARD_CLAUSES]
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
