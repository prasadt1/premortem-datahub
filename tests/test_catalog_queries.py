"""Guards for live catalog honesty: no self-downstream, SQL dedupe, catalog-first."""

from __future__ import annotations

from unittest.mock import patch

from premortem.catalog.fake import FakeCatalogClient
from premortem.catalog.graphql import GraphqlCatalogClient
from premortem.catalog.queries import dedupe_queries_by_sql, filter_self_urn, normalize_sql
from premortem.models import QueryRecord

DEMO_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_history,PROD)"
)


def test_filter_self_urn_drops_subject():
    others = ["urn:li:dataset:downstream_a", DEMO_URN, "urn:li:dataset:downstream_b"]
    assert filter_self_urn(DEMO_URN, others) == [
        "urn:li:dataset:downstream_a",
        "urn:li:dataset:downstream_b",
    ]


def test_fake_get_downstream_excludes_self():
    client = FakeCatalogClient(downstream=[DEMO_URN, "urn:li:dataset:child"])
    assert client.get_downstream(DEMO_URN) == ["urn:li:dataset:child"]


def test_graphql_get_downstream_excludes_self_edge():
    client = GraphqlCatalogClient(gms_url="http://localhost:8080", write_back_enabled=False)

    def fake_post(query, variables=None):
        return {
            "dataset": {
                "relationships": {
                    "relationships": [
                        {"entity": {"urn": DEMO_URN}},
                        {"entity": {"urn": "urn:li:dataset:real_child"}},
                    ]
                }
            }
        }

    with patch.object(client, "_post", side_effect=fake_post):
        assert client.get_downstream(DEMO_URN) == ["urn:li:dataset:real_child"]


def test_normalize_sql_collapses_whitespace_and_case():
    a = "SELECT  order_id\nFROM order_history"
    b = "select order_id from order_history"
    assert normalize_sql(a) == normalize_sql(b)


def test_dedupe_queries_keeps_first_by_normalized_sql():
    records = [
        QueryRecord(query_id="a", sql="SELECT order_id FROM order_history"),
        QueryRecord(query_id="b", sql="select  order_id  from order_history"),
        QueryRecord(query_id="c", sql="SELECT order_status FROM order_history"),
    ]
    out = dedupe_queries_by_sql(records)
    assert [q.query_id for q in out] == ["a", "c"]


def test_fake_get_dataset_queries_dedupes():
    client = FakeCatalogClient(
        queries=[
            QueryRecord(query_id="first", sql="SELECT 1 FROM order_history"),
            QueryRecord(query_id="dup", sql="select 1 from order_history"),
        ]
    )
    rows = client.get_dataset_queries("urn:li:dataset:x")
    assert len(rows) == 1
    assert rows[0].query_id == "first"


def test_graphql_prefers_list_queries_over_seed(tmp_path):
    """Catalog index wins even when a seed file exists (Gate 2 path works)."""
    urn = DEMO_URN
    seed = tmp_path / "seeded_queries.json"
    seed.write_text(
        '{"dataset_urn": "%s", "list_queries_indexed": false, '
        '"queries": [{"query_id": "seed_only", "sql": "SELECT 1 FROM seed_table"}]}'
        % urn,
        encoding="utf-8",
    )
    client = GraphqlCatalogClient(
        gms_url="http://localhost:8080",
        write_back_enabled=False,
        seed_path=str(seed),
    )

    def fake_post(query, variables=None):
        assert "listQueries" in query
        return {
            "listQueries": {
                "total": 2,
                "queries": [
                    {
                        "urn": "urn:li:query:1",
                        "properties": {
                            "name": "catalog_a",
                            "statement": {
                                "value": "SELECT order_id FROM order_history WHERE order_status = 1"
                            },
                        },
                    },
                    {
                        "urn": "urn:li:query:2",
                        "properties": {
                            "name": "catalog_a_dup",
                            "statement": {
                                "value": "select order_id from order_history where order_status = 1"
                            },
                        },
                    },
                ],
            }
        }

    with patch.object(client, "_post", side_effect=fake_post):
        rows = client.get_dataset_queries(urn)
    assert len(rows) == 1
    assert rows[0].query_id == "catalog_a"
    assert "order_status" in rows[0].sql
