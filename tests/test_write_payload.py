"""write_payload — assertion is rung 1; tag + description alongside."""

from __future__ import annotations

from premortem.models import BreakFinding, BreakSeverity, Forecast, SchemaDiff
from premortem.write_payload import CAMERA_ASSERTION_URN, assertion_copy, build_write_payload


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
                query_id="h",
                sql_snippet="SELECT 1 WHERE order_status=1",
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
        unaffected_lineage_count=1,
    )


def test_assertion_copy_is_camera_ready():
    a = assertion_copy(_forecast())
    assert a["urn"] == CAMERA_ASSERTION_URN
    assert a["platform"] == "premortem"
    assert a["field_path"] is None
    assert "rename order_status → order_state" in a["title"]
    assert a["counts"]["hard"] == 1
    assert a["counts"]["cleared"] == 1


def test_write_payload_ladder_assertion_first():
    payload = build_write_payload(_forecast(), markdown="md body")
    assert "assertion" in payload
    assert "tag" in payload
    assert "description" in payload
    assert payload["assertion"]["urn"] == CAMERA_ASSERTION_URN
    assert payload["tag"]["ensure_exists"] is True
    assert "Schema rehearsal" in payload["description"]["markdown"]
