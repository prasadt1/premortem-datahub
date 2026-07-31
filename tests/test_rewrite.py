"""Repair plan: rewrite only subject-bound refs; refuse CLEARED / UNKNOWN / STAR."""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.models import BreakSeverity
from premortem.rewrite import rewrite_sql

SUBJECT = "order_history"
TABLES = {
    "order_history": ["order_id", "order_status", "customer_id"],
    "shipments": ["shipment_id", "order_status", "order_id"],
}


def test_hard_where_emits_patch_renaming_only_subject_ref():
    sql = "SELECT order_id FROM order_history WHERE order_status = 'COMPLETE'"
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "patch"
    assert item.rewritten_sql is not None
    assert "order_state" in item.rewritten_sql
    assert "order_status" not in item.rewritten_sql.lower()
    assert item.unified_diff and "- " in item.unified_diff and "+ " in item.unified_diff


def test_soft_select_emits_patch():
    sql = "SELECT order_status, order_id FROM order_history"
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "patch"
    assert "order_state" in (item.rewritten_sql or "")


def test_cleared_refuses_with_bind_reason():
    sql = "SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'"
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.rewritten_sql is None
    assert item.reason and "shipments" in item.reason
    assert "nothing to fix" in item.reason.lower() or "not the subject" in item.reason.lower()


def test_ambiguous_unknown_refuses_no_guess():
    sql = (
        "SELECT o.order_id FROM order_history o "
        "JOIN shipments s ON o.order_id = s.order_id "
        "WHERE order_status = 'OPEN'"
    )
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.rewritten_sql is None
    assert item.reason and (
        "don't guess" in item.reason.lower() or "ambiguous" in item.reason.lower()
    )


def test_select_star_refuses():
    sql = "SELECT * FROM order_history"
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.reason and ("star" in item.reason.lower() or "*" in item.reason)


def test_join_renames_only_subject_side_not_decoy():
    """Both tables carry order_status; only the subject-qualified ref is rewritten."""
    sql = (
        "SELECT o.order_id FROM order_history o "
        "JOIN shipments s ON o.order_status = s.order_status"
    )
    # Without schemas this is ambiguous; with schemas both sides qualify → both bind?
    # o.order_status → subject HARD; s.order_status → CLEARED path on that hit only.
    # Overall: subject-bound hit exists → HARD; rewrite must change o. only.
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "patch"
    rewritten = item.rewritten_sql or ""
    assert "o.order_state" in rewritten.replace(" ", "").lower() or "order_state" in rewritten
    # shipments side keeps old name
    assert "s.order_status" in rewritten or "shipments" in rewritten.lower()
    assert classify_query(
        rewritten,
        column="order_status",
        subject_table=SUBJECT,
        tables=TABLES,
    ).severity is BreakSeverity.UNAFFECTED
    assert classify_query(
        rewritten,
        column="order_state",
        subject_table=SUBJECT,
        tables={
            "order_history": ["order_id", "order_state", "customer_id"],
            "shipments": ["shipment_id", "order_status", "order_id"],
        },
    ).severity is BreakSeverity.HARD


def test_cte_star_plus_hard_refuses_incomplete_patch():
    """Explicit HARD ref + CTE SELECT * — renaming the WHERE is not a complete fix."""
    sql = (
        "WITH o AS (SELECT * FROM order_history) "
        "SELECT order_id FROM o WHERE order_status = 'OPEN'"
    )
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.reason and (
        "cannot verify completeness" in item.reason.lower()
        or "incomplete" in item.reason.lower()
    )


def test_drop_refuses_no_new_name():
    item = rewrite_sql(
        "SELECT order_status FROM order_history",
        column="order_status",
        new_column=None,
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.reason and "drop" in item.reason.lower()
