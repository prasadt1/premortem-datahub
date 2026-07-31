#!/usr/bin/env python3
"""Repair round-trip over the frozen eval corpus — does not touch labels/schema/corpus.

For every query the binder scores HARD or SOFT: rewrite subject-bound refs to the
new column name, then:

1. re-classify against the *old* column → must be UNAFFECTED
2. re-classify against the *new* column (schema updated) → severity must match original

CLEARED / UNKNOWN / UNAFFECTED → counted as refused (no patch). Exit non-zero if
any patched query fails the round-trip (kill criterion for shipping patches in demo).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from premortem.classify import classify_query
from premortem.models import BreakSeverity
from premortem.rewrite import rewrite_sql

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"


def _load() -> tuple[dict, dict, list[tuple[str, str]]]:
    schema = json.loads((EVAL / "schema.json").read_text(encoding="utf-8"))
    labels = json.loads((EVAL / "labels.json").read_text(encoding="utf-8"))
    queries = []
    for path in sorted((EVAL / "corpus").glob("q*.sql")):
        queries.append((path.stem, path.read_text(encoding="utf-8")))
    return schema, labels, queries


def main() -> int:
    schema, _labels, queries = _load()
    subject = schema["subject"]
    column = subject["column"]
    new_column = subject["change"]["new_column"]
    dialect = subject.get("dialect", "snowflake")
    subject_table = subject["dataset"].split(".")[-1]
    tables: dict[str, list[str]] = dict(schema["tables"])

    # Schema as if the rename already landed (for new-column reclassify)
    tables_after = {
        t: [new_column if c == column else c for c in cols]
        for t, cols in tables.items()
    }

    patched = 0
    passed = 0
    failed: list[str] = []
    refused: dict[str, int] = {}

    print("# Repair round-trip (frozen corpus, binder decisions)\n")
    print("| query | action | detail |")
    print("|---|---|---|")

    for qid, sql in queries:
        item = rewrite_sql(
            sql,
            column=column,
            new_column=new_column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables,
            query_id=qid,
        )
        if item.action == "refuse":
            key = (item.reason or "refuse").split("—")[0].strip()[:48]
            refused[key] = refused.get(key, 0) + 1
            print(f"| {qid} | refuse | {item.reason} |")
            continue

        patched += 1
        assert item.rewritten_sql is not None
        original = classify_query(
            sql,
            column=column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables,
        )
        after_old = classify_query(
            item.rewritten_sql,
            column=column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables,
        )
        after_new = classify_query(
            item.rewritten_sql,
            column=new_column,
            dialect=dialect,
            subject_table=subject_table,
            tables=tables_after,
        )
        ok = (
            after_old.severity is BreakSeverity.UNAFFECTED
            and after_new.severity is original.severity
        )
        if ok:
            passed += 1
            print(
                f"| {qid} | patch ✓ | {original.severity.value} → "
                f"old=unaffected new={after_new.severity.value} |"
            )
        else:
            failed.append(qid)
            print(
                f"| {qid} | patch ✗ | wanted old=unaffected+"
                f"new={original.severity.value}; got old={after_old.severity.value} "
                f"new={after_new.severity.value} |"
            )

    print()
    print("## Summary")
    print(f"- patched: **{patched}**")
    print(f"- round-trip pass: **{passed}/{patched}**")
    print(f"- refused: **{sum(refused.values())}**")
    for reason, n in sorted(refused.items(), key=lambda x: (-x[1], x[0])):
        print(f"  - {reason}: {n}")
    if failed:
        print(f"- FAILED: {', '.join(failed)}")
        return 1
    if patched and passed != patched:
        return 1
    print("- result: **PASS** (100% of eligible patches round-trip)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
