"""CLI — core / offline forecast + Gate 1 write-back."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from premortem.classify import classify_query
from premortem.datahub_client import HttpDataHubClient, write_forecast_to_catalog
from premortem.forecast import build_forecast
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff
from premortem.report import to_json, to_markdown


def _load_queries_from_dir(path: Path) -> list[QueryRecord]:
    files = sorted(path.glob("*.sql"))
    if not files:
        raise SystemExit(f"No .sql files in {path}")
    return [
        QueryRecord(query_id=f.stem, sql=f.read_text(encoding="utf-8")) for f in files
    ]


def _parse_diff(args: argparse.Namespace) -> SchemaDiff:
    if args.rename and args.drop:
        raise SystemExit("--rename and --drop are mutually exclusive")
    if args.rename:
        if ":" not in args.rename:
            raise SystemExit("--rename must be old:new")
        old, new = args.rename.split(":", 1)
        return SchemaDiff(
            dataset_urn=args.urn,
            kind="rename",
            column=old,
            new_column=new,
        )
    if args.drop:
        return SchemaDiff(dataset_urn=args.urn, kind="drop", column=args.drop)
    raise SystemExit("require --rename old:new or --drop column")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="premortem",
        description="Schema-change rehearsal (core / offline / write-back)",
    )
    p.add_argument("--sql-file", help="Classify a single SQL file (no DataHub)")
    p.add_argument("--column", help="Column name")
    p.add_argument("--dialect", default="snowflake")
    p.add_argument(
        "--queries-dir",
        help="Offline: classify all *.sql in directory into a forecast",
    )
    p.add_argument("--urn", default="urn:li:dataset:offline-demo")
    p.add_argument("--rename", help="old:new column rename")
    p.add_argument("--drop", help="column to drop (mutually exclusive with --rename)")
    p.add_argument("--out", help="Write markdown forecast to this path")
    p.add_argument("--json-out", help="Write JSON forecast to this path")
    p.add_argument(
        "--lineage-count",
        type=int,
        default=0,
        help="Impact Analysis baseline dependent count (compose framing)",
    )
    p.add_argument(
        "--use-exec-count",
        action="store_true",
        help="Only after Gate 3 — print (exec×N) when counts exist",
    )
    p.add_argument(
        "--write-back",
        action="store_true",
        help="Write forecast to DataHub (Gate 1 PASS: tag + description / document)",
    )
    p.add_argument(
        "--gms",
        default=os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
        help="GMS URL for --write-back",
    )
    args = p.parse_args(argv)

    if args.sql_file:
        if not args.column:
            p.error("--column is required with --sql-file")
        sql = Path(args.sql_file).read_text(encoding="utf-8")
        r = classify_query(sql, column=args.column, dialect=args.dialect)
        print(f"severity={r.severity.value} evidence={r.evidence}")
        if r.unknown_reason:
            print(f"unknown_reason={r.unknown_reason}")
        if r.severity is BreakSeverity.UNAFFECTED:
            sys.exit(0)
        return

    if args.queries_dir:
        diff = _parse_diff(args)
        queries = _load_queries_from_dir(Path(args.queries_dir))
        forecast = build_forecast(
            diff=diff,
            queries=queries,
            lineage_dependent_count=args.lineage_count,
            dialect=args.dialect,
            use_exec_count=args.use_exec_count,
        )
        md = to_markdown(forecast, use_exec_count=args.use_exec_count)
        js = to_json(forecast, use_exec_count=args.use_exec_count)
        if args.out:
            Path(args.out).write_text(md, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(md)
        if args.json_out:
            Path(args.json_out).write_text(js, encoding="utf-8")
            print(f"wrote {args.json_out}")

        if args.write_back:
            title = f"Premortem: {diff.kind} {diff.column}"
            client = HttpDataHubClient(gms_url=args.gms, write_back_enabled=True)
            ref = write_forecast_to_catalog(
                client, urn=args.urn, title=title, body_md=md
            )
            print(f"write-back ok → {ref}")
        return

    if args.write_back:
        p.error("--write-back requires --queries-dir (and --rename/--drop)")

    print(
        "Core / offline CLI. Live query history after Gate 2.\n"
        "  premortem --sql-file path.sql --column order_status\n"
        "  premortem --queries-dir tests/fixtures/queries "
        "--rename order_status:order_state --lineage-count 12\n"
        "  … --write-back --urn <dataset-urn>   # Gate 1 PASS"
    )


if __name__ == "__main__":
    main()
