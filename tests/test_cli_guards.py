"""CLI guards — lineage baseline must be measured under --live."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from premortem.cli import main


def test_live_rejects_lineage_count_override(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--live", "--rename", "order_status:order_state", "--lineage-count", "12"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--lineage-count cannot be used with --live" in err


def test_live_defaults_adjudicate_off():
    fake = MagicMock()
    fake.markdown = "md"
    fake.json_text = "{}"
    fake.schema_fields = ["order_status"]
    fake.downstream = []
    fake.query_count = 0
    fake.write_back_ref = None
    fake.repairs = []
    with patch("premortem.cli.create_catalog_client"), patch(
        "premortem.cli.run_live_rehearsal", return_value=fake
    ) as run:
        main(["--live", "--rename", "order_status:order_state"])
    assert run.call_args.kwargs["adjudicate"] is False


def test_live_adjudicate_flag_opts_in():
    fake = MagicMock()
    fake.markdown = "md"
    fake.json_text = "{}"
    fake.schema_fields = ["order_status"]
    fake.downstream = []
    fake.query_count = 0
    fake.write_back_ref = None
    fake.repairs = []
    with patch("premortem.cli.create_catalog_client"), patch(
        "premortem.cli.run_live_rehearsal", return_value=fake
    ) as run:
        main(["--live", "--rename", "order_status:order_state", "--adjudicate"])
    assert run.call_args.kwargs["adjudicate"] is True
