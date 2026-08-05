"""CLI — offline fixtures, live DataHub rehearsal, write-back."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from premortem.agent import rehearse
from premortem.catalog.protocol import CatalogError
from premortem.classify import classify_query
from premortem.datahub_client import create_catalog_client, write_forecast_to_catalog
from premortem.gate import parse_fail_on, run_live_gate, run_offline_gate
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.report import to_html, to_json, to_markdown
from premortem.rewrite import build_repairs, emit_patches_to_dir

DEMO_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_history,PROD)"
)

_GMS_HINT = (
    "can't reach DataHub at {url} — the no-catalog path is "
    "python eval/run_eval.py"
)


def _gms_unreachable_message(url: str, exc: BaseException) -> str:
    return f"{_GMS_HINT.format(url=url)}\n({type(exc).__name__}: {exc})"


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


def _gate_main(argv: list[str]) -> int:
    """``premortem gate`` — CI exit code + JSON summary on stdout."""
    p = argparse.ArgumentParser(
        prog="premortem gate",
        description=(
            "Merge gate: exit 0 when no findings meet --fail-on; "
            "non-zero otherwise. JSON summary on stdout."
        ),
    )
    p.add_argument("--live", action="store_true", help="Run against DataHub")
    p.add_argument("--queries-dir", help="Offline: directory of *.sql")
    p.add_argument("--urn", default=DEMO_URN)
    p.add_argument("--rename", help="old:new column rename")
    p.add_argument("--drop", help="column to drop")
    p.add_argument("--dialect", default="snowflake")
    p.add_argument(
        "--fail-on",
        default="hard,unknown",
        help=(
            "Comma list: hard | hard,unknown | hard,soft,unknown "
            "(default: hard,unknown — unparseable must not silent-pass)"
        ),
    )
    p.add_argument(
        "--subject-table",
        help="Offline binder: subject table base name",
    )
    p.add_argument(
        "--tables-json",
        help="Offline binder: JSON tables map (or eval/schema.json shape)",
    )
    p.add_argument(
        "--catalog",
        choices=["kit", "graphql", "fake"],
        default=None,
    )
    p.add_argument(
        "--gms",
        default=os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
    )
    args = p.parse_args(argv)

    try:
        fail_on = parse_fail_on(args.fail_on)
    except ValueError as exc:
        p.error(str(exc))

    if args.live and args.queries_dir:
        p.error("--live and --queries-dir are mutually exclusive")
    if not args.live and not args.queries_dir:
        p.error("require --live or --queries-dir")
    if not args.rename and not args.drop:
        p.error("require --rename old:new or --drop column")

    diff = _parse_diff(args)

    if args.live:
        client = create_catalog_client(backend=args.catalog, gms_url=args.gms)
        try:
            summary = run_live_gate(
                client, diff=diff, fail_on=fail_on, dialect=args.dialect
            )
        except RuntimeError as exc:
            print(f"gate failed: {exc}", file=sys.stderr)
            return 2
        except (CatalogError, ConnectionError, TimeoutError, OSError) as exc:
            print(_gms_unreachable_message(args.gms, exc), file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(
                t in msg
                for t in (
                    "connection",
                    "refused",
                    "failed to establish",
                    "nodename",
                    "name or service",
                    "max retries",
                    "timed out",
                )
            ):
                print(_gms_unreachable_message(args.gms, exc), file=sys.stderr)
                return 2
            raise
    else:
        import json

        tables = None
        if args.tables_json:
            raw = json.loads(Path(args.tables_json).read_text(encoding="utf-8"))
            tables = raw["tables"] if isinstance(raw, dict) and "tables" in raw else raw
        queries = _load_queries_from_dir(Path(args.queries_dir))
        summary = run_offline_gate(
            diff=diff,
            queries=queries,
            fail_on=fail_on,
            dialect=args.dialect,
            subject_table=args.subject_table,
            tables=tables,
        )

    if summary.note:
        print(summary.note, file=sys.stderr)
    print(summary.to_json())
    return summary.exit_code


def _emit(
    forecast_md: str,
    forecast_js: str,
    args: argparse.Namespace,
    *,
    forecast: Forecast | None = None,
    baseline_source: str = "measured",
    notify=None,
) -> None:
    if args.out:
        Path(args.out).write_text(forecast_md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(forecast_md)
    if args.json_out:
        Path(args.json_out).write_text(forecast_js, encoding="utf-8")
        print(f"wrote {args.json_out}")
    if args.html_out:
        fc = forecast if forecast is not None else Forecast.model_validate_json(forecast_js)
        html_doc = to_html(
            fc,
            use_exec_count=args.use_exec_count,
            baseline_source=baseline_source,
            notify=notify,
        )
        Path(args.html_out).write_text(html_doc, encoding="utf-8")
        print(f"wrote {args.html_out}")


def main(argv: list[str] | None = None) -> None:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "gate":
        raise SystemExit(_gate_main(argv_list[1:]))

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
        "--html-out",
        help="Write self-contained HTML report (shareable snapshot for PR/Slack)",
    )
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
        "--catalog",
        choices=["kit", "graphql", "fake"],
        default=None,
        help="Catalog backend (default: kit; set PREMORTEM_CATALOG=graphql to force GraphQL)",
    )
    p.add_argument(
        "--gms",
        default=os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
        help="GMS URL for --live / --write-back",
    )
    p.add_argument(
        "--emit-patches",
        metavar="DIR",
        help=(
            "Write unified diffs for HARD/SOFT repairs into DIR "
            "(CLEARED/UNKNOWN refused — no patch files)"
        ),
    )
    p.add_argument(
        "--subject-table",
        help="Offline binder: subject table base name (required for accurate --emit-patches)",
    )
    p.add_argument(
        "--tables-json",
        help="Offline binder: JSON object mapping table → column list (for --emit-patches)",
    )
    args = p.parse_args(argv_list)

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
            backend=args.catalog,
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
        except (CatalogError, ConnectionError, TimeoutError, OSError) as exc:
            print(_gms_unreachable_message(args.gms, exc), file=sys.stderr)
            sys.exit(2)
        except Exception as exc:  # noqa: BLE001 — judge-facing connection failures
            msg = str(exc).lower()
            if any(
                t in msg
                for t in (
                    "connection",
                    "refused",
                    "failed to establish",
                    "nodename",
                    "name or service",
                    "max retries",
                    "timed out",
                )
            ):
                print(_gms_unreachable_message(args.gms, exc), file=sys.stderr)
                sys.exit(2)
            raise
        print(
            f"# live urn={diff.dataset_urn}\n"
            f"# schema_fields={result.schema_fields}\n"
            f"# sibling_tables={list((result.tables or {}).keys())}\n"
            f"# unresolved={result.unresolved_tables or []}\n"
            f"# queries={result.query_count} downstream={len(result.downstream)}\n"
        )
        _emit(result.markdown, result.json_text, args)
        if args.emit_patches:
            n = emit_patches_to_dir(result.repairs or [], args.emit_patches)
            refused = sum(1 for r in (result.repairs or []) if r.action == "refuse")
            print(
                f"wrote {n} patches to {args.emit_patches} "
                f"({refused} refused — CLEARED/UNKNOWN/STAR/drop)"
            )
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
        tables = None
        if args.tables_json:
            import json

            tables = json.loads(Path(args.tables_json).read_text(encoding="utf-8"))
            if isinstance(tables, dict) and "tables" in tables:
                tables = tables["tables"]
        forecast = rehearse(
            diff=diff,
            queries=queries,
            lineage_dependent_count=lineage_count,
            dialect=args.dialect,
            use_exec_count=args.use_exec_count,
            schema_fields=fields,
            adjudicate=args.adjudicate and not args.no_adjudicate,
            subject_table=args.subject_table,
            tables=tables,
        )
        baseline_source = "user-supplied" if user_supplied else "measured"
        md = to_markdown(
            forecast,
            use_exec_count=args.use_exec_count,
            baseline_source=baseline_source,
        )
        js = to_json(forecast, use_exec_count=args.use_exec_count)
        _emit(
            md,
            js,
            args,
            forecast=forecast,
            baseline_source=baseline_source,
        )

        if args.emit_patches:
            repairs = build_repairs(
                forecast=forecast,
                queries=queries,
                dialect=args.dialect,
                subject_table=args.subject_table,
                tables=tables,
            )
            n = emit_patches_to_dir(repairs, args.emit_patches)
            refused = sum(1 for r in repairs if r.action == "refuse")
            print(
                f"wrote {n} patches to {args.emit_patches} "
                f"({refused} refused — CLEARED/UNKNOWN/STAR/drop)"
            )

        if args.write_back:
            title = f"Premortem: {diff.kind} {diff.column}"
            client = create_catalog_client(
                backend=args.catalog, gms_url=args.gms, write_back_enabled=True
            )
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
        "    … --write-back   # tag + description on the dataset\n"
        "  Merge gate (CI):\n"
        "    premortem gate --queries-dir eval/corpus --rename order_status:order_state "
        "--subject-table order_history --tables-json eval/schema.json --fail-on hard,unknown"
    )


if __name__ == "__main__":
    main()
