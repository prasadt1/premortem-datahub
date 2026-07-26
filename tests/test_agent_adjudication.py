from premortem.agent import (
    Adjudication,
    CallableAdjudicator,
    HeuristicAdjudicator,
    adjudicate_forecast,
    rehearse,
)
from premortem.models import (
    BreakFinding,
    BreakSeverity,
    Forecast,
    QueryRecord,
    SchemaDiff,
)


def test_mock_llm_upgrades_unknown_to_hard():
    finding = BreakFinding(
        query_id="q1",
        sql_snippet="WHERE order_status = 1",
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="WHERE",
        unknown_reason="unqualified with 2 tables",
    )
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:li:dataset:demo",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        lineage_dependent_count=3,
        findings=[finding],
    )
    queries = [
        QueryRecord(
            query_id="q1",
            sql=(
                "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id "
                "WHERE order_status = 1"
            ),
        )
    ]

    def fake_llm(**kwargs):
        return Adjudication(
            severity=BreakSeverity.HARD,
            note="LLM: order_status binds to orders in this join",
        )

    out = adjudicate_forecast(
        forecast,
        queries=queries,
        schema_fields=["order_status", "id", "customer_id"],
        adjudicator=CallableAdjudicator(fake_llm),
    )
    assert len(out.findings) == 1
    assert out.findings[0].severity is BreakSeverity.HARD
    assert out.findings[0].agent_note is not None
    assert "binds to orders" in out.findings[0].agent_note
    assert out.findings[0].unknown_reason is None


def test_heuristic_binds_where_unknown_to_hard():
    sql = (
        "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id "
        "WHERE order_status = 1"
    )
    diff = SchemaDiff(
        dataset_urn="urn:li:dataset:demo",
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    queries = [QueryRecord(query_id="bare", sql=sql)]
    forecast = rehearse(
        diff=diff,
        queries=queries,
        lineage_dependent_count=2,
        adjudicate=True,
        schema_fields=["id", "customer_id", "order_status"],
    )
    by_id = {f.query_id: f for f in forecast.findings}
    assert by_id["bare"].severity is BreakSeverity.HARD
    assert by_id["bare"].agent_note is not None


def test_heuristic_leaves_unknown_without_schema_hit():
    sql = (
        "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id "
        "WHERE order_status = 1"
    )
    adj = HeuristicAdjudicator()
    finding = BreakFinding(
        query_id="bare",
        sql_snippet=sql,
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="WHERE",
        unknown_reason="unqualified",
    )
    result = adj.adjudicate(
        finding=finding,
        sql=sql,
        schema_fields=["id", "customer_id"],  # no order_status
        lineage_neighbors=[],
    )
    assert result is not None
    assert result.severity is BreakSeverity.UNKNOWN
