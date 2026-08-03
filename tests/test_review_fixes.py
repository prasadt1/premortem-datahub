"""Regression tests for review-confirmed footguns and gaps."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from premortem.catalog.fake import FakeCatalogClient
from premortem.cli import main
from premortem.description_merge import merge_premortem_description, strip_premortem_section
from premortem.llm_adjudicator import is_genuine_residue
from premortem.mcp_server import explain_finding_impl, rehearse_schema_change_impl
from premortem.models import BreakFinding, BreakSeverity
from premortem.notify import build_notify, notify_markdown, owner_label
from premortem.rewrite import RepairItem, emit_patches_to_dir
from premortem.write_payload import build_write_payload
from premortem.models import Forecast, SchemaDiff


def test_explain_finding_passes_change_args():
    captured: dict = {}

    def fake_rehearse(**kwargs):
        captured.update(kwargs)
        return {
            "change": {
                "kind": kwargs["change_kind"],
                "column": kwargs["column"],
                "new_name": kwargs["new_name"],
            },
            "adjudicate": kwargs.get("adjudicate", "binder"),
            "findings": [
                {
                    "query_id": "q1",
                    "severity": "hard",
                    "evidence": "WHERE",
                    "sql_snippet": "SELECT 1",
                    "unknown_reason": None,
                    "unknown_kind": None,
                    "agent_note": None,
                    "cleared": False,
                }
            ],
        }

    with patch(
        "premortem.mcp_server.rehearse_schema_change_impl", side_effect=fake_rehearse
    ):
        out = explain_finding_impl(
            query_id="q1",
            dataset="urn:x",
            change_kind="drop",
            column="customer_id",
            new_name=None,
        )
    assert captured["change_kind"] == "drop"
    assert captured["column"] == "customer_id"
    assert captured["new_name"] is None
    assert out["finding"]["query_id"] == "q1"
    assert out["change"]["kind"] == "drop"


def test_rehearse_schema_change_impl_payload_shape():
    fake_result = MagicMock()
    fake_result.forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn="urn:x",
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=[],
    )
    fake_result.markdown = "# md"
    fake_result.downstream = []
    fake_result.tables = {}
    fake_result.unresolved_tables = []
    fake_result.query_count = 0
    fake_result.repairs = []
    client = FakeCatalogClient(fields=["order_status"])
    client.description_by_urn["urn:x"] = "Curated docs stay."

    with patch("premortem.mcp_server._client", return_value=client), patch(
        "premortem.mcp_server.run_live_rehearsal", return_value=fake_result
    ):
        # dataset urn must match description lookup
        fake_result.forecast.diff.dataset_urn = "urn:x"
        out = rehearse_schema_change_impl(
            dataset="urn:x",
            change_kind="rename",
            column="order_status",
            new_name="order_state",
        )
    assert "write_payload" in out
    assert "repairs" in out
    assert "findings" in out
    assert "Curated docs stay." in out["write_payload"]["description"]["markdown"]
    assert "<!-- premortem:forecast -->" in out["write_payload"]["description"]["markdown"]


def test_emit_patches_sanitizes_path_traversal(tmp_path: Path):
    repairs = [
        RepairItem(
            query_id="../../etc/passwd",
            action="patch",
            reason=None,
            severity=BreakSeverity.HARD,
            original_sql="SELECT 1",
            rewritten_sql="SELECT 2",
            unified_diff="--- a\n+++ b\n",
        )
    ]
    n = emit_patches_to_dir(repairs, str(tmp_path))
    assert n == 1
    names = {p.name for p in tmp_path.iterdir()}
    assert "etc" not in names
    assert any(p.name.endswith(".patch") for p in tmp_path.iterdir())
    # Must not escape tmp_path
    for p in tmp_path.rglob("*"):
        assert tmp_path in p.resolve().parents or p.resolve() == tmp_path


def test_description_merge_preserves_curated_text():
    existing = "Team runbook.\n\nContact oncall."
    merged = merge_premortem_description(existing, "## Schema rehearsal\n\nbody")
    assert "Team runbook." in merged
    assert "Contact oncall." in merged
    assert "<!-- premortem:forecast -->" in merged
    again = merge_premortem_description(merged, "## Schema rehearsal\n\nnew body")
    assert again.count("<!-- premortem:forecast -->") == 1
    assert "new body" in again
    assert "body" not in again.split("premortem:forecast")[-1] or "new body" in again


def test_owner_label_bare_name_with_urn_secondary():
    urn = "urn:li:corpuser:b2fd91.brock1@example.com"
    label = owner_label(urn)
    assert label.startswith("b2fd91.brock1@example.com")
    assert urn in label


def test_notify_mixed_ownership():
    subject = "urn:li:dataset:order_history"
    down = "urn:li:dataset:shipments"
    client = FakeCatalogClient(
        owners={subject: ["urn:li:corpuser:alex_orders"]}
        # shipments intentionally unowned
    )
    forecast = Forecast(
        diff=SchemaDiff(
            dataset_urn=subject,
            kind="rename",
            column="order_status",
            new_column="order_state",
        ),
        findings=[
            BreakFinding(
                query_id="q1",
                sql_snippet="x",
                severity=BreakSeverity.HARD,
                column="order_status",
                evidence="WHERE",
            )
        ],
    )
    md = notify_markdown(
        build_notify(
            client, subject_urn=subject, downstream=[down], forecast=forecast
        )
    )
    assert "alex_orders" in md
    assert "no owners recorded" in md
    assert down in md


def test_is_genuine_residue_uses_unknown_kind_not_prose():
    finding = BreakFinding(
        query_id="q",
        sql_snippet="x",
        severity=BreakSeverity.UNKNOWN,
        column="order_status",
        evidence="WHERE",
        unknown_reason="totally reworded human prose with no tables phrase",
        unknown_kind="ambiguous_bare",
    )
    assert is_genuine_residue(finding) is True
    finding2 = finding.model_copy(
        update={"unknown_kind": "parse", "unknown_reason": "unqualified `x` with 2 tables in scope"}
    )
    assert is_genuine_residue(finding2) is False


def test_gate_live_unreachable_is_friendly(capsys):
    with patch("premortem.cli.create_catalog_client"), patch(
        "premortem.cli.run_live_gate",
        side_effect=ConnectionError("Connection refused"),
    ):
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    "gate",
                    "--live",
                    "--rename",
                    "order_status:order_state",
                    "--gms",
                    "http://localhost:8080",
                ]
            )
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "can't reach DataHub at http://localhost:8080" in err
    assert "python eval/run_eval.py" in err


def test_live_unreachable_is_friendly(capsys):
    with patch("premortem.cli.create_catalog_client"), patch(
        "premortem.cli.run_live_rehearsal",
        side_effect=ConnectionError("Failed to establish a new connection"),
    ):
        with pytest.raises(SystemExit) as exc:
            main(["--live", "--rename", "order_status:order_state", "--gms", "http://127.0.0.1:9"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "can't reach DataHub" in err
    assert "eval/run_eval.py" in err


def test_seed_refuses_non_localhost(monkeypatch):
    import importlib.util
    from pathlib import Path

    # The seeder imports the DataHub SDK at module scope; skip on the light
    # install path (`pip install -e ".[dev]"`) the README's judge path uses.
    pytest.importorskip("datahub")

    path = Path(__file__).resolve().parents[1] / "tools" / "seed_demo_environment.py"
    spec = importlib.util.spec_from_file_location("seed_demo_environment", path)
    assert spec and spec.loader
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    monkeypatch.setattr(seed, "GMS", "https://prod.datahub.example/gms")
    with pytest.raises(SystemExit) as exc:
        seed.require_local_gms(allow_remote=False)
    assert "refusing to mutate" in str(exc.value)


def test_cli_emit_patches_offline(tmp_path: Path, capsys):
    q = tmp_path / "hard.sql"
    q.write_text(
        "SELECT order_id FROM order_history WHERE order_status = 'X'\n",
        encoding="utf-8",
    )
    tables = tmp_path / "tables.json"
    tables.write_text(
        json.dumps({"order_history": ["order_id", "order_status"]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "patches"
    main(
        [
            "--queries-dir",
            str(tmp_path),
            "--rename",
            "order_status:order_state",
            "--subject-table",
            "order_history",
            "--tables-json",
            str(tables),
            "--emit-patches",
            str(out_dir),
        ]
    )
    assert any(out_dir.glob("*.patch"))
    assert "wrote" in capsys.readouterr().out
