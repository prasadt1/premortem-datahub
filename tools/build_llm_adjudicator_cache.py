#!/usr/bin/env python3
"""Populate eval/llm_adjudicator_cache.json for genuine residue UNKNOWNs.

Calls Claude CLI (temperature mindset: conservative JSON). Commit the cache so
``python eval/run_eval.py`` reproduces B2 with no API key.

Usage:
  python tools/build_llm_adjudicator_cache.py
  python tools/build_llm_adjudicator_cache.py --dry-run   # list residue only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from premortem.agent import rehearse  # noqa: E402
from premortem.classify import classify_query  # noqa: E402
from premortem.llm_adjudicator import (  # noqa: E402
    ResidueLlmAdjudicator,
    is_genuine_residue,
)
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff  # noqa: E402

EVAL = ROOT / "eval"
CACHE = EVAL / "llm_adjudicator_cache.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache", type=Path, default=CACHE)
    args = ap.parse_args()

    schema = json.loads((EVAL / "schema.json").read_text())
    labels = json.loads((EVAL / "labels.json").read_text())
    column = schema["subject"]["column"]
    dialect = schema["subject"].get("dialect", "snowflake")
    subject = schema["subject"]["dataset"]
    tables = schema["tables"]

    residue_ids = []
    for case in labels["cases"]:
        sql = (EVAL / "corpus" / f"{case['id']}.sql").read_text(encoding="utf-8")
        result = classify_query(
            sql,
            column=column,
            dialect=dialect,
            subject_table=subject,
            tables=tables,
        )
        finding_like = type(
            "F",
            (),
            {
                "severity": result.severity,
                "unknown_reason": result.unknown_reason,
                "evidence": result.evidence,
                "column": column,
                "query_id": case["id"],
            },
        )()
        # minimal BreakFinding-compatible
        from premortem.models import BreakFinding

        f = BreakFinding(
            query_id=case["id"],
            sql_snippet=sql[:200],
            severity=result.severity,
            column=column,
            evidence=result.evidence,
            unknown_reason=result.unknown_reason,
        )
        if is_genuine_residue(f):
            residue_ids.append(case["id"])
            print(f"residue {case['id']} gold={case['gold']} reason={result.unknown_reason}")

    print(f"residue count: {len(residue_ids)}")
    if args.dry_run:
        return 0

    queries = []
    for case in labels["cases"]:
        sql = (EVAL / "corpus" / f"{case['id']}.sql").read_text(encoding="utf-8")
        queries.append(QueryRecord(query_id=case["id"], sql=sql))

    diff = SchemaDiff(
        dataset_urn=f"eval:{subject}",
        kind=schema["subject"]["change"]["kind"],
        column=column,
        new_column=schema["subject"]["change"].get("new_column"),
    )
    adj = ResidueLlmAdjudicator(
        tables=tables,
        subject_table=subject,
        cache_path=args.cache,
        allow_network=True,
    )
    # Seed empty cache structure
    if not args.cache.is_file():
        args.cache.write_text(
            json.dumps(
                {
                    "version": 1,
                    "model": "claude-cli",
                    "temperature": 0,
                    "entries": {},
                    "note": "Committed so eval B2 reproduces without API credentials.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        adj.cache = json.loads(args.cache.read_text(encoding="utf-8"))

    forecast = rehearse(
        diff=diff,
        queries=queries,
        dialect=dialect,
        schema_fields=tables[subject],
        adjudicate=True,
        adjudicator=adj,
        subject_table=subject,
        tables=tables,
    )
    for f in forecast.findings:
        if f.query_id in residue_ids:
            print(
                f"adjudicated {f.query_id} -> {f.severity.value} note={f.agent_note}"
            )
    print(f"cache entries: {len(adj.cache.get('entries', {}))} -> {args.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
