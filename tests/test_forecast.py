from premortem.forecast import build_forecast
from premortem.models import BreakSeverity, QueryRecord, SchemaDiff
from premortem.report import to_markdown


def test_build_forecast_classifies_mix():
    diff = SchemaDiff(
        dataset_urn="urn:li:dataset:demo",
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    queries = [
        QueryRecord(query_id="h1", sql="SELECT id FROM orders WHERE order_status = 1"),
        QueryRecord(query_id="s1", sql="SELECT order_status, id FROM orders"),
        QueryRecord(
            query_id="u1",
            sql=(
                "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id "
                "WHERE order_status = 1"
            ),
        ),
        QueryRecord(query_id="n1", sql="SELECT id FROM orders WHERE amount > 1"),
    ]
    forecast = build_forecast(
        diff=diff,
        queries=queries,
        lineage_dependent_count=4,
        use_exec_count=False,
    )
    by_id = {f.query_id: f for f in forecast.findings}
    assert by_id["h1"].severity is BreakSeverity.HARD
    assert by_id["s1"].severity is BreakSeverity.SOFT
    assert by_id["u1"].severity is BreakSeverity.UNKNOWN
    assert "n1" not in by_id
    assert forecast.unaffected_lineage_count == 1
    md = to_markdown(forecast, use_exec_count=False)
    assert "Impact Analysis baseline: 4" in md
    assert "HARD (1)" in md
    assert "SOFT (1)" in md
    assert "UNKNOWN / needs human (1)" in md
    assert "No query evidence of `order_status` on subject: 1" in md
    assert "exec×" not in md
