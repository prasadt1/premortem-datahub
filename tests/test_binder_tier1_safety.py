"""Tier-1 binder safety: refuse instead of guessing on unconfident binding."""

from __future__ import annotations

from premortem.classify import classify_query
from premortem.gate import evaluate_gate, parse_fail_on
from premortem.models import BreakFinding, BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.rewrite import build_repairs, rewrite_sql

SUBJECT = "order_history"
TABLES = {
    "order_history": ["order_id", "order_status", "customer_id"],
    "shipments": ["shipment_id", "order_status", "order_id"],
    "analytics.order_history": ["order_id", "order_status", "customer_id"],
    "logistics.shipments": ["shipment_id", "order_status", "order_id"],
}


def _c(sql: str):
    return classify_query(
        sql,
        column="order_status",
        dialect="snowflake",
        subject_table=SUBJECT,
        tables=TABLES,
    )


def test_alias_shadowed_by_cte_is_unknown_not_cleared():
    """Outer s IS order_history; CTE also named s over shipments — must not CLEARED."""
    sql = (
        "WITH s AS (SELECT order_status FROM logistics.shipments) "
        "SELECT s.order_status FROM analytics.order_history AS s"
    )
    r = _c(sql)
    assert r.severity is BreakSeverity.UNKNOWN, (
        f"shadowed alias must be UNKNOWN not {r.severity.value} ({r.evidence})"
    )
    assert r.unknown_kind == "alias_shadowed"
    assert "reused across scopes" in (r.unknown_reason or "")


def test_alias_shadowed_subquery_does_not_emit_patch_for_wrong_table():
    """Outer s is shipments; inner subquery reuses s for order_history — no patch."""
    sql = (
        "SELECT s.order_status FROM logistics.shipments AS s "
        "WHERE s.order_id IN ("
        "  SELECT s.order_id FROM analytics.order_history AS s"
        ")"
    )
    r = _c(sql)
    assert r.severity is BreakSeverity.UNKNOWN
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"
    assert item.rewritten_sql is None


def test_distinct_aliases_still_clear_and_bind():
    """Control: distinct aliases — CLEARED / HARD still work."""
    cleared = _c(
        "SELECT s.shipment_id FROM logistics.shipments s WHERE s.order_status = 'X'"
    )
    assert cleared.severity is BreakSeverity.UNAFFECTED
    assert cleared.evidence.startswith("BOUND_ELSEWHERE:")

    hard = _c(
        "SELECT o.order_id FROM analytics.order_history o WHERE o.order_status = 'X'"
    )
    assert hard.severity is BreakSeverity.HARD


def test_derived_table_alias_is_unknown_not_subject_soft():
    sql = (
        "SELECT t.order_status FROM analytics.order_history o "
        "JOIN (SELECT order_status FROM logistics.shipments) t ON 1=1"
    )
    r = _c(sql)
    assert r.severity is BreakSeverity.UNKNOWN
    assert r.unknown_kind == "unresolvable_qualifier"
    item = rewrite_sql(
        sql,
        column="order_status",
        new_column="order_state",
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert item.action == "refuse"


def test_update_set_is_hard_not_soft():
    r = _c("UPDATE analytics.order_history SET order_status = 'X' WHERE order_id = 1")
    assert r.severity is BreakSeverity.HARD
    assert "SET" in r.evidence or "UPDATE" in r.evidence


def test_insert_column_list_is_hard():
    r = _c(
        "INSERT INTO analytics.order_history (order_id, order_status) VALUES (1, 'X')"
    )
    assert r.severity is BreakSeverity.HARD


def test_merge_update_set_is_hard():
    r = _c(
        "MERGE INTO analytics.order_history t USING logistics.shipments s "
        "ON t.order_id = s.order_id "
        "WHEN MATCHED THEN UPDATE SET order_status = s.order_status"
    )
    assert r.severity is BreakSeverity.HARD


def test_gate_default_fail_on_includes_unknown():
    assert BreakSeverity.UNKNOWN in parse_fail_on("hard,unknown")
    # CLI default is hard,unknown — unparseable must trigger
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:x",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=[
            BreakFinding(
                query_id="jinja",
                sql_snippet="{{ ref('x') }}",
                severity=BreakSeverity.UNKNOWN,
                column="order_status",
                evidence="PARSE",
                unknown_kind="parse",
            )
        ],
    )
    summary = evaluate_gate(forecast, fail_on=parse_fail_on("hard,unknown"))
    assert summary.clean is False
    assert summary.exit_code == 1


def test_gate_hard_only_with_unparseable_gets_unread_exit():
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:x",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=[
            BreakFinding(
                query_id="jinja",
                sql_snippet="{{ ref('x') }}",
                severity=BreakSeverity.UNKNOWN,
                column="order_status",
                evidence="PARSE",
                unknown_kind="parse",
            )
        ],
    )
    summary = evaluate_gate(forecast, fail_on=parse_fail_on("hard"))
    assert summary.exit_code == 2
    assert summary.clean is False


def test_duplicate_query_id_refuses_repair():
    diff = SchemaDiff(
        dataset_urn="urn:x",
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    forecast = Forecast(
        diff=diff,
        findings=[
            BreakFinding(
                query_id="same",
                sql_snippet="SELECT order_status FROM order_history",
                severity=BreakSeverity.SOFT,
                column="order_status",
                evidence="SELECT",
            )
        ],
    )
    queries = [
        QueryRecord(
            query_id="same",
            sql="SELECT order_status FROM order_history",
        ),
        QueryRecord(
            query_id="same",
            sql="SELECT order_status FROM order_history WHERE order_status = 'X'",
        ),
    ]
    repairs = build_repairs(
        forecast=forecast,
        queries=queries,
        subject_table=SUBJECT,
        tables=TABLES,
    )
    assert len(repairs) == 1
    assert repairs[0].action == "refuse"
    assert "duplicate query_id" in (repairs[0].reason or "")
