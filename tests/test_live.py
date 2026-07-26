from premortem.datahub_client import FakeDataHubClient
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff


def test_live_rehearsal_with_fake_client():
    urn = "urn:li:dataset:demo"
    client = FakeDataHubClient(
        fields=["order_id", "order_status", "customer_id"],
        downstream=["urn:li:dataset:downstream_a"],
        queries=[
            QueryRecord(
                query_id="hard",
                sql="SELECT id FROM orders WHERE order_status = 1",
                dataset_urn=urn,
            ),
            QueryRecord(
                query_id="bare",
                sql=(
                    "SELECT o.id FROM orders o JOIN customers c "
                    "ON o.customer_id = c.id WHERE order_status = 1"
                ),
                dataset_urn=urn,
            ),
            QueryRecord(
                query_id="soft",
                sql="SELECT order_status, id FROM orders",
                dataset_urn=urn,
            ),
        ],
        write_back_enabled=True,
    )
    diff = SchemaDiff(
        dataset_urn=urn,
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    result = run_live_rehearsal(
        client,
        diff=diff,
        adjudicate=True,
        write_back=True,
    )
    assert result.query_count == 3
    assert result.schema_fields == ["customer_id", "order_id", "order_status"]
    assert len(result.downstream) == 1
    assert result.forecast.lineage_dependent_count == 1
    by_id = {f.query_id: f for f in result.forecast.findings}
    assert by_id["hard"].severity is BreakSeverity.HARD
    assert by_id["soft"].severity is BreakSeverity.SOFT
    assert by_id["bare"].severity is BreakSeverity.HARD  # adjudicated
    assert by_id["bare"].agent_note is not None
    assert "Impact Analysis baseline: 1" in result.markdown
    assert result.write_back_ref is not None
    assert client.saved_docs or client.added_tags or client.descriptions


def test_live_rehearsal_rejects_missing_column():
    client = FakeDataHubClient(fields=["order_id"], queries=[])
    diff = SchemaDiff(
        dataset_urn="urn:li:dataset:demo",
        kind="drop",
        column="order_status",
    )
    try:
        run_live_rehearsal(client, diff=diff, adjudicate=False)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "not in schema" in str(e) or "no queries" in str(e) or "no schema" in str(e)
