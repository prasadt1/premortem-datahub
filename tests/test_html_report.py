from premortem.models import BreakFinding, BreakSeverity, Forecast, SchemaDiff
from premortem.notify import NotifyTarget
from premortem.report import to_html


def _forecast() -> Forecast:
    return Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:li:dataset:demo",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        lineage_dependent_count=3,
        findings=[
            BreakFinding(
                query_id="hard_where",
                sql_snippet="SELECT 1 FROM t WHERE order_status = 'X'",
                severity=BreakSeverity.HARD,
                column="order_status",
                evidence="WHERE",
            ),
            BreakFinding(
                query_id="decoy",
                sql_snippet="SELECT s.order_status FROM shipments s",
                severity=BreakSeverity.UNAFFECTED,
                column="order_status",
                evidence="BOUND_ELSEWHERE:shipments",
            ),
        ],
    )


def test_html_report_contains_verdict_counts_and_escapes():
    html = to_html(_forecast(), use_exec_count=False)
    assert html.startswith("<!DOCTYPE html>")
    assert "HARD — breaks on deploy (1)" in html
    assert "CLEARED — false alarm (1)" in html
    assert "hard_where" in html
    assert "Impact Analysis baseline: 3" in html
    assert "<script" not in html.lower()


def test_html_includes_notify_when_provided():
    notify = [
        NotifyTarget(
            urn="urn:li:dataset:down",
            role="downstream",
            owners=("alice@corp",),
            worst_severity=BreakSeverity.HARD,
        )
    ]
    html = to_html(_forecast(), use_exec_count=False, notify=notify)
    assert "<h2>Notify</h2>" in html
    assert "alice@corp" in html
