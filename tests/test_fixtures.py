from pathlib import Path

import pytest

from premortem.classify import classify_query
from premortem.models import BreakSeverity

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = FIXTURES / "expected.json"


def test_frozen_fixture_labels():
    import json

    data = json.loads(EXPECTED.read_text(encoding="utf-8"))
    column = data["column"]
    dialect = data["dialect"]
    for case in data["cases"]:
        sql = (FIXTURES / "queries" / case["file"]).read_text(encoding="utf-8")
        r = classify_query(sql, column=column, dialect=dialect)
        assert r.severity is BreakSeverity(case["severity"]), case["file"]
        if "evidence_contains" in case:
            assert case["evidence_contains"] in r.evidence, case["file"]


@pytest.mark.parametrize(
    "filename,severity",
    [
        ("hard_where.sql", BreakSeverity.HARD),
        ("soft_select.sql", BreakSeverity.SOFT),
        ("unknown_bare_join.sql", BreakSeverity.UNKNOWN),
    ],
)
def test_named_fixtures(filename, severity):
    sql = (FIXTURES / "queries" / filename).read_text(encoding="utf-8")
    r = classify_query(sql, column="order_status", dialect="snowflake")
    assert r.severity is severity
