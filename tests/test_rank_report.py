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
    assert "exec×" not in md
    assert "HARD (1)" in md
