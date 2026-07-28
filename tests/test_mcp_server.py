"""Premortem MCP — thin wrapper; no business logic in the server."""

from __future__ import annotations

from premortem.mcp_server import write_back_forecast_impl


def test_write_back_gated_by_default():
    out = write_back_forecast_impl(
        dataset="urn:li:dataset:x",
        title="t",
        markdown="m",
        apply_via_library=False,
    )
    assert out["status"] == "skipped"
    assert "DataHub MCP" in out["reason"]
