from premortem.classify import classify_query
from premortem.models import BreakSeverity


def test_where_is_hard():
    sql = "SELECT id FROM orders WHERE order_status = 1"
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.HARD
    assert "WHERE" in r.evidence


def test_select_only_is_soft():
    sql = "SELECT order_status, id FROM orders"
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.SOFT


def test_unqualified_in_multi_table_join_is_unknown():
    sql = """
    SELECT o.id, c.name FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE order_status = 1
    """
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.UNKNOWN
    assert r.unknown_reason is not None


def test_qualified_in_join_is_hard():
    sql = """
    SELECT o.id FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE o.order_status = 1
    """
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.HARD


def test_unaffected():
    sql = "SELECT id FROM orders WHERE amount > 10"
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.UNAFFECTED


def test_parse_failure_is_unknown():
    r = classify_query("NOT VALID SQL (((", column="order_status", dialect="snowflake")
    assert r.severity is BreakSeverity.UNKNOWN
    assert r.unknown_reason is not None
