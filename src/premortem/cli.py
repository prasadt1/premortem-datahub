"""CLI stub — full DataHub wiring after verification gates."""

from __future__ import annotations

import argparse
import sys

from premortem.classify import classify_query
from premortem.models import BreakSeverity


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="premortem", description="Schema-change rehearsal (core)")
    p.add_argument("--sql-file", help="Classify a single SQL file (no DataHub)")
    p.add_argument("--column", required=False, help="Column name for --sql-file mode")
    p.add_argument("--dialect", default="snowflake")
    args = p.parse_args(argv)

    if args.sql_file:
        if not args.column:
            p.error("--column is required with --sql-file")
        sql = open(args.sql_file, encoding="utf-8").read()
        r = classify_query(sql, column=args.column, dialect=args.dialect)
        print(f"severity={r.severity.value} evidence={r.evidence}")
        if r.unknown_reason:
            print(f"unknown_reason={r.unknown_reason}")
        if r.severity is BreakSeverity.UNAFFECTED:
            sys.exit(0)
        return

    print(
        "Core-only CLI. Live DataHub mode lands after Gate 1–2.\n"
        "Try: premortem --sql-file path.sql --column order_status"
    )


if __name__ == "__main__":
    main()
