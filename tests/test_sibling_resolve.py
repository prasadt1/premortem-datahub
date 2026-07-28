"""Sibling-table schema resolution — live path matches eval multi-table binder."""

from __future__ import annotations

from premortem.catalog.fake import FakeCatalogClient
from premortem.catalog.resolve import (
    extract_physical_table_names,
    pick_best_urn,
    resolve_sibling_schemas,
)
from premortem.classify import classify_query
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff

SUBJECT = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_history,PROD)"
)
CUSTOMERS = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.order_entry.customers,PROD)"
)
SHIPMENTS = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.shipments,PROD)"
)


def test_extract_physical_tables_ignores_cte_alias():
    sql = """
    WITH t AS (SELECT order_id, order_status FROM order_history)
    SELECT order_id FROM t WHERE order_status = 'OPEN'
    """
    assert extract_physical_table_names(sql) == {"order_history"}


def test_pick_best_urn_prefers_same_platform():
    hits = [
        "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.customers,PROD)",
        CUSTOMERS,
    ]
    assert pick_best_urn("customers", hits, subject_urn=SUBJECT) == CUSTOMERS


def test_resolve_sibling_schemas_builds_tables_map():
    client = FakeCatalogClient(
        fields=["order_id", "order_status", "customer_id"],
        search_index={
            "customers": [CUSTOMERS],
            "shipments": [SHIPMENTS],
        },
    )
    client.schemas_by_urn = {
        SUBJECT: ["order_id", "order_status", "customer_id"],
        CUSTOMERS: ["customer_id", "customer_name"],
        SHIPMENTS: ["shipment_id", "order_id", "order_status", "carrier"],
    }
    sqls = [
        "SELECT o.order_id FROM order_history o JOIN customers c "
        "ON o.customer_id = c.customer_id WHERE order_status = 'OPEN'",
        "SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'",
    ]
    res = resolve_sibling_schemas(
        client,
        subject_urn=SUBJECT,
        subject_table="order_history",
        subject_fields=["order_id", "order_status", "customer_id"],
        sql_statements=sqls,
    )
    assert "customers" in res.tables
    assert "order_status" not in res.tables["customers"]
    assert "order_status" in res.tables["shipments"]
    assert res.unresolved == []


def test_narrowable_join_becomes_hard_with_sibling_schema():
    tables = {
        "order_history": ["order_id", "customer_id", "order_status"],
        "customers": ["customer_id", "customer_name"],
    }
    sql = (
        "SELECT o.order_id FROM order_history o JOIN customers c "
        "ON o.customer_id = c.customer_id WHERE order_status = 'OPEN'"
    )
    r = classify_query(
        sql,
        column="order_status",
        dialect="snowflake",
        subject_table="order_history",
        tables=tables,
    )
    assert r.severity is BreakSeverity.HARD


def test_unresolved_sibling_reason_string():
    tables = {"order_history": ["order_id", "order_status"]}
    sql = (
        "SELECT o.order_id FROM order_history o JOIN mystery m "
        "ON o.order_id = m.order_id WHERE order_status = 'OPEN'"
    )
    r = classify_query(
        sql,
        column="order_status",
        dialect="snowflake",
        subject_table="order_history",
        tables=tables,
    )
    assert r.severity is BreakSeverity.UNKNOWN
    assert r.unknown_reason is not None
    assert "couldn't resolve table mystery" in r.unknown_reason
    assert "not guessing" in r.unknown_reason


def test_live_rehearsal_uses_sibling_resolution():
    client = FakeCatalogClient(
        fields=["order_id", "order_status", "customer_id"],
        downstream=["urn:li:dataset:child"],
        search_index={"customers": [CUSTOMERS], "shipments": [SHIPMENTS]},
        queries=[
            QueryRecord(
                query_id="narrowable",
                sql=(
                    "SELECT o.order_id FROM order_history o JOIN customers c "
                    "ON o.customer_id = c.customer_id WHERE order_status = 'OPEN'"
                ),
                dataset_urn=SUBJECT,
            ),
            QueryRecord(
                query_id="decoy",
                sql="SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'",
                dataset_urn=SUBJECT,
            ),
            QueryRecord(
                query_id="ambiguous",
                sql=(
                    "SELECT o.order_id FROM order_history o JOIN shipments s "
                    "ON o.order_id = s.order_id WHERE order_status = 'OPEN'"
                ),
                dataset_urn=SUBJECT,
            ),
        ],
    )
    client.schemas_by_urn = {
        SUBJECT: ["order_id", "order_status", "customer_id"],
        CUSTOMERS: ["customer_id", "name"],
        SHIPMENTS: ["shipment_id", "order_id", "order_status"],
    }
    diff = SchemaDiff(
        dataset_urn=SUBJECT,
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    result = run_live_rehearsal(client, diff=diff, adjudicate=False)
    by_id = {f.query_id: f for f in result.forecast.findings}
    assert by_id["narrowable"].severity is BreakSeverity.HARD
    assert by_id["ambiguous"].severity is BreakSeverity.UNKNOWN
    assert "decoy" not in by_id  # UNAFFECTED
    assert result.tables is not None
    assert "shipments" in result.tables
