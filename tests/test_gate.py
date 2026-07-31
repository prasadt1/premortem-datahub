"""Merge gate — exit code over fail-on thresholds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from premortem.cli import main
from premortem.gate import evaluate_gate, parse_fail_on
from premortem.models import BreakFinding, BreakSeverity, Forecast, SchemaDiff


def _forecast(*sevs: BreakSeverity) -> Forecast:
    findings = [
        BreakFinding(
            query_id=f"q{i}",
            sql_snippet="SELECT 1",
            severity=sev,
            column="order_status",
            evidence="WHERE" if sev is BreakSeverity.HARD else "SELECT",
        )
        for i, sev in enumerate(sevs)
    ]
    return Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:x",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=findings,
    )


def test_parse_fail_on_default_hard():
    assert parse_fail_on("hard") == frozenset({BreakSeverity.HARD})


def test_parse_fail_on_multi():
    assert parse_fail_on("hard,unknown") == frozenset(
        {BreakSeverity.HARD, BreakSeverity.UNKNOWN}
    )


def test_gate_clean_when_only_soft_and_fail_on_hard():
    s = evaluate_gate(_forecast(BreakSeverity.SOFT), fail_on=parse_fail_on("hard"))
    assert s.clean is True
    assert s.exit_code == 0
    assert s.triggered == []


def test_gate_fails_on_hard():
    s = evaluate_gate(
        _forecast(BreakSeverity.SOFT, BreakSeverity.HARD),
        fail_on=parse_fail_on("hard"),
    )
    assert s.clean is False
    assert s.exit_code == 1
    assert "q1" in s.triggered


def test_gate_cli_offline_fails(tmp_path: Path, capsys):
    q = tmp_path / "hard.sql"
    q.write_text(
        "SELECT order_id FROM order_history WHERE order_status = 'X'\n",
        encoding="utf-8",
    )
    tables = tmp_path / "tables.json"
    tables.write_text(
        json.dumps(
            {
                "order_history": ["order_id", "order_status"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "gate",
                "--queries-dir",
                str(tmp_path),
                "--rename",
                "order_status:order_state",
                "--subject-table",
                "order_history",
                "--tables-json",
                str(tables),
                "--fail-on",
                "hard",
            ]
        )
    assert exc.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["clean"] is False
    assert out["counts"]["hard"] >= 1


def test_gate_cli_offline_clean_soft_only(tmp_path: Path, capsys):
    q = tmp_path / "soft.sql"
    q.write_text(
        "SELECT order_status FROM order_history\n",
        encoding="utf-8",
    )
    tables = tmp_path / "tables.json"
    tables.write_text(
        json.dumps({"order_history": ["order_id", "order_status"]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "gate",
                "--queries-dir",
                str(tmp_path),
                "--rename",
                "order_status:order_state",
                "--subject-table",
                "order_history",
                "--tables-json",
                str(tables),
                "--fail-on",
                "hard",
            ]
        )
    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["clean"] is True
