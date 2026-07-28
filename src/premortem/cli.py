"""CLI — offline fixtures, live DataHub rehearsal, write-back."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from premortem.agent import rehearse
from premortem.classify import classify_query
from premortem.datahub_client import create_catalog_client, write_forecast_to_catalog
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff
from premortem.report import to_json, to_markdown

DEMO_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_history,PROD)"
)


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


def _emit(forecast_md: str, forecast_js: str, args: argparse.Namespace) -> None:
    if args.out:
        Path(args.out).write_text(forecast_md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(forecast_md)
    if args.json_out:
        Path(args.json_out).write_text(forecast_js, encoding="utf-8")
        print(f"wrote {args.json_out}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="premortem",
        description="Schema-change rehearsal (offline / live DataHub / write-back)",
    )
    p.add_argument("--sql-file", help="Classify a single SQL file (no DataHub)")
    p.add_argument("--column", help="Column name")
    p.add_argument("--dialect", default="snowflake")
    p.add_argument(
        "--queries-dir",
        help="Offline: classify all *.sql in directory into a forecast",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Fetch schema, lineage, and queries from DataHub for --urn",
    )
    p.add_argument("--urn", default=DEMO_URN)
    p.add_argument("--rename", help="old:new column rename")
    p.add_argument("--drop", help="column to drop (mutually exclusive with --rename)")
    p.add_argument("--out", help="Write markdown forecast to this path")
    p.add_argument("--json-out", help="Write JSON forecast to this path")
    p.add_argument(
        "--lineage-count",
        type=int,
        default=None,
        help="Override Impact Analysis baseline count (default: live downstream len)",
    )
    p.add_argument(
        "--use-exec-count",
        action="store_true",
        help="Only after Gate 3 — print (exec×N) when counts exist",
    )
    p.add_argument(
        "--write-back",
        action="store_true",
        help="Write forecast to DataHub (tag + description / document)",
    )
    p.add_argument(
        "--adjudicate",
        action="store_true",
        help=(
            "Opt in to heuristic UNKNOWN adjudication (net-negative on frozen eval; "
            "off by default — binder-only classify is the live path)"
        ),
    )
    p.add_argument(
        "--no-adjudicate",
        action="store_true",
        help="Explicitly disable adjudication (default; kept for clarity)",
    )
    p.add_argument(
        "--schema-fields",
        help="Comma-separated schema fields for offline adjudication",
    )
    p.add_argument(
        "--gms",
        default=os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
        help="GMS URL for --live / --write-back",
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

    if args.live:
        if args.queries_dir:
            p.error("--live and --queries-dir are mutually exclusive")
        if args.lineage_count is not None:
            p.error(
                "--lineage-count cannot be used with --live "
                "(baseline must be measured from get_downstream; never hand-set)"
            )
        if not args.rename and not args.drop:
            p.error("--live requires --rename old:new or --drop column")
        diff = _parse_diff(args)
        # Binder-only is the default (classify.py). Heuristic adjudicate is opt-in:
        # frozen eval shows C+A net-negative vs C (bind accuracy 0.00 on residue).
        adjudicate = bool(args.adjudicate) and not args.no_adjudicate
        client = create_catalog_client(
            gms_url=args.gms,
            write_back_enabled=args.write_back,
        )
        try:
            result = run_live_rehearsal(
                client,
                diff=diff,
                dialect=args.dialect,
                use_exec_count=args.use_exec_count,
                adjudicate=adjudicate,
                write_back=args.write_back,
                lineage_count_override=None,
            )
        except RuntimeError as exc:
            print(f"live rehearsal failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            f"# live urn={diff.dataset_urn}\n"
            f"# schema_fields={result.schema_fields}\n"
            f"# sibling_tables={list((result.tables or {}).keys())}\n"
            f"# unresolved={result.unresolved_tables or []}\n"
            f"# queries={result.query_count} downstream={len(result.downstream)}\n"
        )
        _emit(result.markdown, result.json_text, args)
        if result.write_back_ref:
            print(f"write-back ok → {result.write_back_ref}")
        return

    if args.queries_dir:
        diff = _parse_diff(args)
        queries = _load_queries_from_dir(Path(args.queries_dir))
        fields = (
            [f.strip() for f in args.schema_fields.split(",") if f.strip()]
            if args.schema_fields
            else [diff.column]
        )
        user_supplied = args.lineage_count is not None
        lineage_count = args.lineage_count if user_supplied else 0
        forecast = rehearse(
            diff=diff,
            queries=queries,
            lineage_dependent_count=lineage_count,
            dialect=args.dialect,
            use_exec_count=args.use_exec_count,
            schema_fields=fields,
            adjudicate=args.adjudicate and not args.no_adjudicate,
        )
        baseline_source = "user-supplied" if user_supplied else "measured"
        md = to_markdown(
            forecast,
            use_exec_count=args.use_exec_count,
            baseline_source=baseline_source,
        )
        js = to_json(forecast, use_exec_count=args.use_exec_count)
        _emit(md, js, args)

        if args.write_back:
            title = f"Premortem: {diff.kind} {diff.column}"
            client = create_catalog_client(gms_url=args.gms, write_back_enabled=True)
            ref = write_forecast_to_catalog(
                client, urn=args.urn, title=title, body_md=md
            )
            print(f"write-back ok → {ref}")
        return

    if args.write_back:
        p.error("--write-back requires --live or --queries-dir")

    print(
        "Schema-change rehearsal CLI.\n"
        "  Offline:\n"
        "    premortem --queries-dir tests/fixtures/queries "
        "--rename order_status:order_state --lineage-count 12 --adjudicate\n"
        "  Live DataHub (Quickstart):\n"
        "    premortem --live --rename order_status:order_state "
        "--out examples/forecast-order-status.md\n"
        "    premortem --live --drop order_status --out examples/forecast-drop-order-status.md\n"
        "    … --write-back   # tag + description on the dataset"
    )


if __name__ == "__main__":
    main()
