from premortem.models import BreakFinding, BreakSeverity, Forecast, SchemaDiff
from premortem.rank import rank_findings
from premortem.report import to_markdown


def _f(qid: str, sev: BreakSeverity, exec_count: int | None = None) -> BreakFinding:
    return BreakFinding(
        query_id=qid,
        sql_snippet="SELECT 1",
        severity=sev,
        column="order_status",
        evidence="WHERE",
        exec_count=exec_count,
    )


def test_rank_hard_before_soft_without_counts():
    findings = [
        _f("b", BreakSeverity.SOFT),
        _f("a", BreakSeverity.HARD),
        _f("c", BreakSeverity.UNKNOWN),
    ]
    ranked = rank_findings(findings, use_exec_count=False)
    assert [f.severity for f in ranked] == [
        BreakSeverity.HARD,
        BreakSeverity.SOFT,
        BreakSeverity.UNKNOWN,
    ]


def test_markdown_omits_exec_when_none():
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:li:dataset:demo",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        lineage_dependent_count=12,
        findings=[_f("q1", BreakSeverity.HARD)],
    )
    md = to_markdown(forecast, use_exec_count=False)
    assert "Impact Analysis baseline: 12" in md
    assert "baseline: user-supplied" not in md
    assert "exec×" not in md
    assert "HARD (1)" in md


def test_markdown_marks_user_supplied_baseline():
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:li:dataset:demo",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        lineage_dependent_count=12,
        findings=[_f("q1", BreakSeverity.HARD)],
    )
    md = to_markdown(
        forecast, use_exec_count=False, baseline_source="user-supplied"
    )
    assert "Impact Analysis baseline: 12 downstream dependents (baseline: user-supplied)" in md


def test_markdown_renders_cleared_decoy_section():
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:li:dataset:demo",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        lineage_dependent_count=3,
        findings=[
            BreakFinding(
                query_id="decoy_shipments_order_status",
                sql_snippet="SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'",
                severity=BreakSeverity.UNAFFECTED,
                column="order_status",
                evidence="BOUND_ELSEWHERE:shipments",
            ),
            BreakFinding(
                query_id="unknown_bare",
                sql_snippet="SELECT o.order_id FROM order_history o JOIN shipments s WHERE order_status = 'OPEN'",
                severity=BreakSeverity.UNKNOWN,
                column="order_status",
                evidence="WHERE",
                unknown_reason="unqualified",
            ),
        ],
        unaffected_lineage_count=1,
    )
    md = to_markdown(forecast, use_exec_count=False)
    assert "CLEARED (references a same-named column that binds elsewhere) (1)" in md
    assert "decoy_shipments_order_status — binds to `shipments`" in md
    assert "unknown_bare" in md
    assert "UNKNOWN / needs human (1)" in md
    assert "`SELECT" in md or "SELECT" in md  # snippet wrapped or collapsed
    assert "No query evidence of `order_status` on subject: 1" in md
    assert "UNAFFECTED / no query evidence" not in md
