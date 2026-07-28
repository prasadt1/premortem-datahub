"""Adversarial fixtures for binder P0 (decoy / SELECT * / CTE).

Tune against tests/; measure against eval/ (do not read eval/labels.json while fixing).
"""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.models import BreakSeverity

SUBJECT = "order_history"
TABLES = {
    "order_history": [
        "order_id",
        "customer_id",
        "order_status",
        "order_total",
    ],
    "shipments": [
        "shipment_id",
        "order_id",
        "order_status",
        "carrier",
    ],
    "crm.tickets": [
        "ticket_id",
        "order_status",
        "priority",
    ],
}


def _classify(sql: str):
    return classify_query(
        sql,
        column="order_status",
        dialect="snowflake",
        subject_table=SUBJECT,
        tables=TABLES,
    )


# ---------------------------------------------------------------------------
# Decoy: qualified reference to another table's same-named column
# ---------------------------------------------------------------------------


def test_decoy_qualified_other_table_should_be_unaffected():
    sql = "SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'"
    r = _classify(sql)
    assert r.severity is BreakSeverity.UNAFFECTED, (
        "qualified other-table order_status must not count as a hit on "
        f"analytics.order_history; got {r.severity.value} evidence={r.evidence}"
    )
    assert r.evidence.startswith("BOUND_ELSEWHERE:")
    assert "shipments" in r.evidence


def test_decoy_unrelated_dataset_groupby_should_be_unaffected():
    sql = "SELECT order_status, COUNT(*) FROM crm.tickets GROUP BY order_status"
    r = _classify(sql)
    assert r.severity is BreakSeverity.UNAFFECTED, (
        "subject dataset not in scope → UNAFFECTED; "
        f"got {r.severity.value}"
    )
    assert r.evidence.startswith("BOUND_ELSEWHERE:")
    assert "tickets" in r.evidence


# ---------------------------------------------------------------------------
# SELECT * over subject → UNKNOWN (needs schema to expand); never UNAFFECTED
# ---------------------------------------------------------------------------


def test_select_star_over_subject_should_be_unknown():
    sql = "SELECT * FROM order_history"
    r = _classify(sql)
    assert r.severity is BreakSeverity.UNKNOWN, (
        "SELECT * hides column references — honest label is UNKNOWN; "
        f"got {r.severity.value}"
    )


# ---------------------------------------------------------------------------
# CTE single-source must not inflate table count into spurious UNKNOWN
# Mirrors eval shapes: q25 HARD (filter), q07 SOFT (projection-only).
# ---------------------------------------------------------------------------


def test_cte_single_source_filter_should_be_hard():
    sql = """
    WITH t AS (SELECT order_id, order_status FROM order_history)
    SELECT order_id FROM t WHERE order_status = 'OPEN'
    """
    r = _classify(sql)
    assert r.severity is BreakSeverity.HARD, (
        "single real source via CTE — CTE name must not count as a second table; "
        f"got {r.severity.value} evidence={r.evidence} reason={r.unknown_reason}"
    )


def test_cte_single_source_projection_should_be_soft():
    sql = """
    WITH t AS (SELECT order_id, order_status FROM order_history)
    SELECT order_status FROM t WHERE order_id > 1
    """
    r = _classify(sql)
    assert r.severity is BreakSeverity.SOFT, (
        "projection-only via single-source CTE is SOFT, not UNKNOWN/HARD; "
        f"got {r.severity.value} evidence={r.evidence} reason={r.unknown_reason}"
    )
