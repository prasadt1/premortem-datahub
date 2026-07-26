from unittest.mock import patch

import json

import pytest

from premortem.datahub_client import (
    FORECAST_TAG_URN,
    FakeDataHubClient,
    GraphqlError,
    HttpDataHubClient,
    WriteBackDisabledError,
    write_forecast_to_catalog,
)
from premortem.models import QueryRecord


def test_fake_reads_queries():
    client = FakeDataHubClient(
        fields=["order_status", "id"],
        downstream=["urn:li:dataset:downstream"],
        queries=[
            QueryRecord(query_id="q1", sql="SELECT order_status FROM orders"),
        ],
    )
    assert client.list_schema_fields("u") == ["order_status", "id"]
    assert client.get_downstream("u") == ["urn:li:dataset:downstream"]
    assert client.get_dataset_queries("u")[0].query_id == "q1"


def test_write_back_disabled_by_default():
    client = FakeDataHubClient()
    with pytest.raises(WriteBackDisabledError):
        client.add_tags("urn:li:dataset:x", ["urn:li:tag:t"])
    with pytest.raises(WriteBackDisabledError):
        client.save_forecast_document("urn:li:dataset:x", "t", "# body")
    with pytest.raises(WriteBackDisabledError):
        client.update_description("urn:li:dataset:x", "desc")


def test_write_back_enabled_records():
    client = FakeDataHubClient(write_back_enabled=True)
    client.add_tags("urn:li:dataset:x", ["urn:li:tag:t"])
    doc = client.save_forecast_document("urn:li:dataset:x", "title", "# md")
    client.update_description("urn:li:dataset:x", "desc")
    assert client.added_tags == [("urn:li:dataset:x", ["urn:li:tag:t"])]
    assert doc.startswith("urn:li:document:")
    assert client.descriptions == [("urn:li:dataset:x", "desc")]


def test_http_write_back_disabled():
    client = HttpDataHubClient(write_back_enabled=False)
    with pytest.raises(WriteBackDisabledError):
        client.add_tags("urn:li:dataset:x", ["urn:li:tag:t"])


def test_http_add_tags_posts_graphql():
    client = HttpDataHubClient(gms_url="http://localhost:8080", write_back_enabled=True)
    with patch.object(client, "_post", return_value={"batchAddTags": True}) as post:
        client.add_tags("urn:li:dataset:x", ["urn:li:tag:t"])
        assert post.called
        variables = post.call_args[0][1]
        assert variables["input"]["tagUrns"] == ["urn:li:tag:t"]


def test_http_save_forecast_falls_back_to_tag_and_description():
    client = HttpDataHubClient(gms_url="http://localhost:8080", write_back_enabled=True)
    calls: list[str] = []

    def fake_post(query: str, variables=None):
        calls.append(query)
        if "createDocument" in query:
            raise GraphqlError("documents not available")
        if "createTag" in query:
            return {"createTag": FORECAST_TAG_URN}
        if "batchAddTags" in query:
            return {"batchAddTags": True}
        if "updateDescription" in query:
            return {"updateDescription": True}
        raise AssertionError(query)

    with patch.object(client, "_post", side_effect=fake_post):
        ref = client.save_forecast_document(
            "urn:li:dataset:x", "Premortem", "# forecast"
        )
    assert "description+tag:" in ref
    assert any("batchAddTags" in c for c in calls)
    assert any("updateDescription" in c for c in calls)


def test_http_save_forecast_also_updates_description_when_doc_ok():
    client = HttpDataHubClient(gms_url="http://localhost:8080", write_back_enabled=True)
    calls: list[str] = []

    def fake_post(query: str, variables=None):
        calls.append(query)
        if "createDocument" in query:
            return {"createDocument": "urn:li:document:abc"}
        if "createTag" in query:
            return {"createTag": FORECAST_TAG_URN}
        if "batchAddTags" in query:
            return {"batchAddTags": True}
        if "updateDescription" in query:
            return {"updateDescription": True}
        raise AssertionError(query)

    with patch.object(client, "_post", side_effect=fake_post):
        ref = client.save_forecast_document(
            "urn:li:dataset:x", "Premortem", "# forecast"
        )
    assert "urn:li:document:abc" in ref
    assert "description+tag:" in ref
    assert any("updateDescription" in c for c in calls)


def test_http_queries_from_seed_file(tmp_path):
    seed = tmp_path / "seeded_queries.json"
    urn = "urn:li:dataset:demo"
    seed.write_text(
        json.dumps(
            {
                "dataset_urn": urn,
                "queries": [
                    {
                        "query_id": "q1",
                        "sql": "SELECT order_status FROM orders",
                        "exec_count": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    client = HttpDataHubClient(
        gms_url="http://localhost:8080",
        write_back_enabled=False,
        seed_path=str(seed),
    )
    with patch.object(client, "_post", side_effect=GraphqlError("listQueries empty")):
        rows = client.get_dataset_queries(urn)
    assert len(rows) == 1
    assert rows[0].query_id == "q1"
    assert "order_status" in rows[0].sql
