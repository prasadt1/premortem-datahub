"""Who-to-warn / Notify section."""

from __future__ import annotations

from premortem.catalog.fake import FakeCatalogClient
from premortem.models import BreakFinding, BreakSeverity, Forecast, QueryRecord, SchemaDiff
from premortem.notify import build_notify, notify_markdown
from premortem.report import to_markdown


SUBJECT = "urn:li:dataset:order_history"
DOWN = "urn:li:dataset:shipments"


def _forecast(sev: BreakSeverity) -> Forecast:
    return Forecast(
        diff=SchemaDiff(
            dataset_urn=SUBJECT,
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=[
            BreakFinding(
                query_id="q1",
                sql_snippet="SELECT 1",
                severity=sev,
                column="order_status",
                evidence="WHERE",
            )
        ],
        lineage_dependent_count=1,
    )


def test_notify_lists_owners_grouped_by_severity():
    client = FakeCatalogClient(
        owners={
            SUBJECT: ["urn:li:corpuser:alex_orders"],
            DOWN: ["urn:li:corpuser:sam_logistics"],
        }
    )
    targets = build_notify(
        client,
        subject_urn=SUBJECT,
        downstream=[DOWN],
        forecast=_forecast(BreakSeverity.HARD),
    )
    md = notify_markdown(targets)
    assert "HARD priority" in md
    assert "alex_orders" in md
    assert "sam_logistics" in md


def test_notify_honest_when_no_owners():
    client = FakeCatalogClient(owners={})
    targets = build_notify(
        client,
        subject_urn=SUBJECT,
        downstream=[DOWN],
        forecast=_forecast(BreakSeverity.UNKNOWN),
    )
    md = notify_markdown(targets)
    assert "no owners recorded in DataHub" in md


def test_report_includes_notify_section():
    client = FakeCatalogClient(
        owners={SUBJECT: ["urn:li:corpuser:alex_orders"]},
    )
    forecast = _forecast(BreakSeverity.SOFT)
    notify = build_notify(
        client, subject_urn=SUBJECT, downstream=[], forecast=forecast
    )
    md = to_markdown(forecast, use_exec_count=False, notify=notify)
    assert "Notify (who to warn before Friday)" in md
    assert "alex_orders" in md
