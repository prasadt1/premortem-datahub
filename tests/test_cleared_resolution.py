"""CLEARED requires positive resolution to a known non-subject table.

Regression for the mozilla/bigquery-etl false-CLEARED defect: any qualifier
that was not the subject was cleared, including STRUCT paths, UNNEST aliases,
and unresolvable names.
"""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.models import BreakSeverity

SUBJECT = "clients_daily_v6"
TABLES = {
    "clients_daily_v6": ["client_id", "submission_date", "country", "events"],
    "shipments": ["shipment_id", "client_id", "order_id"],
}


def _c(sql: str):
    return classify_query(
        sql,
        column="client_id",
        dialect="bigquery",
        subject_table=SUBJECT,
        tables=TABLES,
    )


def test_struct_path_on_subject_where_is_hard():
    """BigQuery STRUCT field on the subject table — not a different table."""
    sql = (
        "SELECT submission_date FROM clients_daily_v6 "
        "WHERE client_info.client_id = 'abc'"
    )
    r = _c(sql)
    assert r.severity is BreakSeverity.HARD, (
        f"struct path on subject must be HARD; got {r.severity.value} "
        f"evidence={r.evidence} reason={r.unknown_reason}"
    )


def test_struct_path_on_subject_select_is_soft():
    sql = "SELECT client_info.client_id FROM clients_daily_v6"
    r = _c(sql)
    assert r.severity is BreakSeverity.SOFT, (
        f"struct path SELECT-only on subject must be SOFT; got {r.severity.value} "
        f"evidence={r.evidence} reason={r.unknown_reason}"
    )


def test_unnest_alias_qualifier_is_unknown():
    sql = (
        "SELECT e.client_id FROM clients_daily_v6, UNNEST(events) AS e"
    )
    r = _c(sql)
    assert r.severity is BreakSeverity.UNKNOWN, (
        f"UNNEST alias is not a table — UNKNOWN; got {r.severity.value} "
        f"evidence={r.evidence} reason={r.unknown_reason}"
    )
    assert r.unknown_reason and "couldn't resolve qualifier" in r.unknown_reason


def test_unresolvable_table_qualifier_is_unknown():
    sql = "SELECT some_unknown_table.client_id FROM some_unknown_table"
    r = _c(sql)
    assert r.severity is BreakSeverity.UNKNOWN, (
        f"unresolvable table must be UNKNOWN not CLEARED; got {r.severity.value} "
        f"evidence={r.evidence} reason={r.unknown_reason}"
    )
    assert r.unknown_reason and "couldn't resolve qualifier" in r.unknown_reason


def test_known_non_subject_table_still_cleared():
    """Positive resolution to shipments (in schema map) remains CLEARED."""
    sql = "SELECT s.shipment_id FROM shipments s WHERE s.client_id = 'x'"
    r = _c(sql)
    assert r.severity is BreakSeverity.UNAFFECTED
    assert r.evidence.startswith("BOUND_ELSEWHERE:")
    assert "shipments" in r.evidence
