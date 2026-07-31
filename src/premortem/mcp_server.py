"""Premortem MCP server — thin wrapper over the library (spec §3.4).

Tools:
  rehearse_schema_change  — on-camera; returns forecast + write_payload
  explain_finding         — never on camera
  write_back_forecast     — gated; host normally applies write_payload via DataHub MCP

Run:
  DATAHUB_TELEMETRY_ENABLED=false python -m premortem.mcp_server

Claude Code / Cursor MCP config should register this alongside DataHub's MCP
server so the tool-call log shows DataHub for context reads and Premortem for
rehearsal.
"""

from __future__ import annotations

import json
import os
from typing import Any

from premortem.catalog import create_catalog_client, write_forecast_to_catalog
from premortem.cli import DEMO_URN
from premortem.forecast import is_cleared_finding
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, SchemaDiff
from premortem.write_payload import build_write_payload

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None  # type: ignore[misc, assignment]


mcp = FastMCP("premortem") if FastMCP is not None else None


def _client(*, write_back: bool = False):
    return create_catalog_client(
        gms_url=os.environ.get("DATAHUB_GMS_URL"),
        token=os.environ.get("DATAHUB_GMS_TOKEN")
        or os.environ.get("DATAHUB_TOKEN"),
        write_back_enabled=write_back,
    )


def rehearse_schema_change_impl(
    *,
    dataset: str = DEMO_URN,
    change_kind: str = "rename",
    column: str = "order_status",
    new_name: str | None = "order_state",
    adjudicate: str = "binder",
) -> dict[str, Any]:
    """Run a live rehearsal; adjudicate='binder' means classify-only (default)."""
    if change_kind not in {"rename", "drop"}:
        raise ValueError("change_kind must be 'rename' or 'drop'")
    if change_kind == "rename" and not new_name:
        raise ValueError("new_name required for rename")
    diff = SchemaDiff(
        dataset_urn=dataset,
        kind=change_kind,
        column=column,
        new_column=new_name if change_kind == "rename" else None,
    )
    # binder = adjudicate False; anything else opts into heuristic (net-negative)
    do_adjudicate = adjudicate not in {"binder", "off", "false", "0", ""}
    client = _client(write_back=False)
    result = run_live_rehearsal(
        client,
        diff=diff,
        adjudicate=do_adjudicate,
        write_back=False,
    )
    payload = build_write_payload(result.forecast, markdown=result.markdown)
    findings = []
    for f in result.forecast.findings:
        findings.append(
            {
                "query_id": f.query_id,
                "severity": f.severity.value,
                "evidence": f.evidence,
                "sql_snippet": f.sql_snippet,
                "unknown_reason": f.unknown_reason,
                "cleared": is_cleared_finding(f.evidence),
            }
        )
    return {
        "dataset": dataset,
        "change": {
            "kind": change_kind,
            "column": column,
            "new_name": new_name,
        },
        "adjudicate": "binder" if not do_adjudicate else adjudicate,
        "lineage_dependent_count": result.forecast.lineage_dependent_count,
        "downstream": result.downstream,
        "sibling_tables": list((result.tables or {}).keys()),
        "unresolved_tables": result.unresolved_tables or [],
        "query_count": result.query_count,
        "markdown": result.markdown,
        "findings": findings,
        "write_payload": payload,
        "repairs": [r.as_dict() for r in (result.repairs or [])],
    }


def explain_finding_impl(*, query_id: str, dataset: str = DEMO_URN) -> dict[str, Any]:
    """Evidence detail for one query_id from a fresh binder rehearsal."""
    result = rehearse_schema_change_impl(dataset=dataset)
    for f in result["findings"]:
        if f["query_id"] == query_id:
            return {"query_id": query_id, "finding": f}
    return {
        "query_id": query_id,
        "finding": None,
        "note": "query_id not in latest rehearsal findings "
        "(may be NO_REFERENCE / no query evidence)",
    }


def write_back_forecast_impl(
    *,
    dataset: str,
    title: str,
    markdown: str,
    apply_via_library: bool = False,
) -> dict[str, Any]:
    """Gated write. Prefer host applying write_payload via DataHub MCP.

    When apply_via_library=True, Premortem uses its catalog client (tag +
    description). Assertion upsert stays on the host / seeder path.
    """
    if not apply_via_library:
        return {
            "status": "skipped",
            "reason": (
                "Host agent should apply write_payload as-is via DataHub MCP "
                "(add_tags / update_description / upsertCustomAssertion). "
                "Pass apply_via_library=true only for offline demos."
            ),
        }
    client = _client(write_back=True)
    ref = write_forecast_to_catalog(
        client, urn=dataset, title=title, body_md=markdown
    )
    return {"status": "ok", "ref": ref}


if mcp is not None:

    @mcp.tool()
    def rehearse_schema_change(
        dataset: str = DEMO_URN,
        change_kind: str = "rename",
        column: str = "order_status",
        new_name: str | None = "order_state",
        adjudicate: str = "binder",
    ) -> str:
        """Rehearse a schema change: HARD/SOFT/UNKNOWN/CLEARED forecast + write_payload
        + repairs (HARD/SOFT patches; CLEARED/UNKNOWN refused).

        On-camera tool. adjudicate='binder' (default) uses classify-only.
        Host applies write_payload via DataHub MCP — do not recompute.
        """
        return json.dumps(
            rehearse_schema_change_impl(
                dataset=dataset,
                change_kind=change_kind,
                column=column,
                new_name=new_name,
                adjudicate=adjudicate,
            ),
            indent=2,
        )

    @mcp.tool()
    def explain_finding(query_id: str, dataset: str = DEMO_URN) -> str:
        """Detail one finding by query_id. Never on camera."""
        return json.dumps(
            explain_finding_impl(query_id=query_id, dataset=dataset), indent=2
        )

    @mcp.tool()
    def write_back_forecast(
        dataset: str,
        title: str,
        markdown: str,
        apply_via_library: bool = False,
    ) -> str:
        """Gated write-back. Prefer DataHub MCP applying write_payload as-is."""
        return json.dumps(
            write_back_forecast_impl(
                dataset=dataset,
                title=title,
                markdown=markdown,
                apply_via_library=apply_via_library,
            ),
            indent=2,
        )


def main() -> None:
    if FastMCP is None:
        raise SystemExit(
            "mcp package required: pip install 'mcp[cli]' "
            "(or pip install -e '.[mcp]')"
        )
    # Filming: keep telemetry off so retries don't scroll the session.
    os.environ.setdefault("DATAHUB_TELEMETRY_ENABLED", "false")
    assert mcp is not None
    mcp.run()


if __name__ == "__main__":
    main()
