"""CLI guards — lineage baseline must be measured under --live."""

from __future__ import annotations

import pytest

from premortem.cli import main


def test_live_rejects_lineage_count_override(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--live", "--rename", "order_status:order_state", "--lineage-count", "12"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--lineage-count cannot be used with --live" in err
