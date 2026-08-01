"""Repair plan: rewrite subject-bound column refs; refuse when binding is honest-no.

Reuses ``analyze_bindings`` — never a second binder. Patch policy:

- HARD / SOFT → unified diff renaming only subject-bound refs
- CLEARED → refuse (binds elsewhere — nothing to fix)
- UNKNOWN / STAR / PARSE → refuse (I don't guess on production SQL)
- drop (no new_column) → refuse
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Literal

from sqlglot import exp

from premortem.classify import analyze_bindings
from premortem.forecast import is_cleared_finding
from premortem.models import BreakSeverity, Forecast, QueryRecord


@dataclass
class RepairItem:
    query_id: str
    action: Literal["patch", "refuse"]
    reason: str | None
    severity: BreakSeverity | None
    original_sql: str
    rewritten_sql: str | None
    unified_diff: str | None

    def as_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "action": self.action,
            "reason": self.reason,
            "severity": self.severity.value if self.severity else None,
            "original_sql": self.original_sql,
            "rewritten_sql": self.rewritten_sql,
            "unified_diff": self.unified_diff,
        }


def _refuse(
    *,
    query_id: str,
    sql: str,
    reason: str,
    severity: BreakSeverity | None = None,
) -> RepairItem:
    return RepairItem(
        query_id=query_id,
        action="refuse",
        reason=reason,
        severity=severity,
        original_sql=sql,
        rewritten_sql=None,
        unified_diff=None,
    )


def _unified_diff(original: str, rewritten: str, *, query_id: str) -> str:
    a = original if original.endswith("\n") else original + "\n"
    b = rewritten if rewritten.endswith("\n") else rewritten + "\n"
    return "".join(
        difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile=f"a/{query_id}.sql",
            tofile=f"b/{query_id}.sql",
        )
    )


def rewrite_sql(
    sql: str,
    *,
    column: str,
    new_column: str | None,
    dialect: str = "snowflake",
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
    query_id: str = "query",
) -> RepairItem:
    """Emit a patch for HARD/SOFT subject-bound refs, or refuse with a stated reason."""
    if not new_column:
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason="drop — no rewritten column name; refuse rather than invent a fix",
        )

    analysis = analyze_bindings(
        sql,
        column=column,
        dialect=dialect,
        subject_table=subject_table,
        tables=tables,
    )

    if analysis.severity is BreakSeverity.UNKNOWN:
        if analysis.evidence == "STAR":
            reason = (
                "SELECT * over the subject — can't rewrite what isn't enumerated"
            )
        else:
            reason = (
                "ambiguous binding — I don't guess on your production SQL"
                + (f" ({analysis.unknown_reason})" if analysis.unknown_reason else "")
            )
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason=reason,
            severity=BreakSeverity.UNKNOWN,
        )

    if analysis.severity is BreakSeverity.UNAFFECTED:
        if is_cleared_finding(analysis.evidence):
            bound = analysis.evidence.split(":", 1)[-1]
            return _refuse(
                query_id=query_id,
                sql=sql,
                reason=(
                    f"binds to {bound}, not the subject — nothing to fix"
                ),
                severity=BreakSeverity.UNAFFECTED,
            )
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason="no subject-bound reference — nothing to fix",
            severity=BreakSeverity.UNAFFECTED,
        )

    if analysis.severity not in (BreakSeverity.HARD, BreakSeverity.SOFT):
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason=f"unexpected severity {analysis.severity.value}",
            severity=analysis.severity,
        )

    if analysis.tree is None or not analysis.subject_bound_nodes:
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason="no subject-bound column nodes to rewrite",
            severity=analysis.severity,
        )

    for node in analysis.subject_bound_nodes:
        node.set("this", exp.to_identifier(new_column))

    rewritten = analysis.tree.sql(dialect=dialect)

    # Incomplete if residual refs or SELECT * still hides the old column.
    residual = analyze_bindings(
        rewritten,
        column=column,
        dialect=dialect,
        subject_table=subject_table,
        tables=tables,
    )
    if residual.severity is not BreakSeverity.UNAFFECTED:
        reason = (
            "cannot verify completeness (star may still reference the old column)"
            if residual.evidence == "STAR"
            else (
                "incomplete repair — residual reference remains "
                f"({residual.severity.value}: {residual.evidence})"
            )
        )
        return _refuse(
            query_id=query_id,
            sql=sql,
            reason=reason,
            severity=analysis.severity,
        )

    return RepairItem(
        query_id=query_id,
        action="patch",
        reason=None,
        severity=analysis.severity,
        original_sql=sql,
        rewritten_sql=rewritten,
        unified_diff=_unified_diff(sql, rewritten, query_id=query_id),
    )


def build_repairs(
    *,
    forecast: Forecast,
    queries: list[QueryRecord],
    dialect: str = "snowflake",
    subject_table: str | None = None,
    tables: dict[str, list[str]] | None = None,
) -> list[RepairItem]:
    """One repair decision per finding (HARD/SOFT patch; CLEARED/UNKNOWN refuse)."""
    by_id = {q.query_id: q for q in queries}
    out: list[RepairItem] = []
    for finding in forecast.findings:
        q = by_id.get(finding.query_id)
        sql = q.sql if q is not None else finding.sql_snippet
        out.append(
            rewrite_sql(
                sql,
                column=forecast.diff.column,
                new_column=forecast.diff.new_column,
                dialect=dialect,
                subject_table=subject_table,
                tables=tables,
                query_id=finding.query_id,
            )
        )
    return out


def emit_patches_to_dir(repairs: list[RepairItem], directory: str) -> int:
    """Write ``*.patch`` files for patched items. Returns count written."""
    import hashlib
    import re
    from pathlib import Path

    def _safe_id(query_id: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", query_id)
        cleaned = cleaned.strip("._") or "query"
        if cleaned in {".", ".."} or ".." in cleaned:
            cleaned = "query"
        cleaned = cleaned[:100]
        digest = hashlib.sha1(query_id.encode("utf-8")).hexdigest()[:8]
        return f"{cleaned}-{digest}"

    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    n = 0
    for item in repairs:
        if item.action != "patch" or not item.unified_diff:
            continue
        safe = _safe_id(item.query_id)
        patch_path = (root / f"{safe}.patch").resolve()
        try:
            patch_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"refusing path escape for query_id={item.query_id!r}"
            ) from exc
        patch_path.write_text(item.unified_diff, encoding="utf-8")
        if item.rewritten_sql is not None:
            sql_path = (root / f"{safe}.rewritten.sql").resolve()
            try:
                sql_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"refusing path escape for query_id={item.query_id!r}"
                ) from exc
            sql_path.write_text(
                item.rewritten_sql
                + ("\n" if not item.rewritten_sql.endswith("\n") else ""),
                encoding="utf-8",
            )
        n += 1
    return n


__all__ = [
    "RepairItem",
    "build_repairs",
    "emit_patches_to_dir",
    "rewrite_sql",
]
