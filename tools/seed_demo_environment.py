#!/usr/bin/env python3
"""Seed the local Quickstart demo environment for Premortem video beats.

Idempotent against http://localhost:8080 (or DATAHUB_GMS_URL):

1. Snowflake ``analytics.shipments`` dataset (+ schema with ``order_status``)
2. Lineage: shipments / order_details / order_details_replica ← ORDER_HISTORY
3. QUERY entities for decoy + truly-ambiguous demo beats
4. Exactly one camera-ready custom assertion (stable URN, upsert not append)

Usage:
  python tools/seed_demo_environment.py
  python tools/seed_demo_environment.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    AuditStampClass,
    DatasetPropertiesClass,
    OtherSchemaClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StringTypeClass,
)

from premortem.catalog import create_catalog_client
from premortem.cli import DEMO_URN
from premortem.live import run_live_rehearsal
from premortem.models import BreakSeverity, SchemaDiff
from premortem.write_payload import CAMERA_ASSERTION_URN, assertion_copy

GMS = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")

SHIPMENTS_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.shipments,PROD)"
)
ORDER_DETAILS_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_details,PROD)"
)
ORDER_DETAILS_REPLICA_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_details_replica,PROD)"
)

DECOY_SQL = "SELECT s.shipment_id FROM shipments s WHERE s.order_status = 'SHIPPED'"
AMBIGUOUS_SQL = (
    "SELECT o.order_id FROM order_history o JOIN shipments s "
    "ON o.order_id = s.order_id WHERE order_status = 'OPEN'"
)

ASSERTION_URN_FILE = Path(__file__).resolve().parents[1] / "examples" / "s2_assertion_urn.txt"
FORECAST_URL = (
    "https://github.com/prasadt1/premortem-datahub/blob/main/examples/forecast-order-status.md"
)


def gql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        GMS + "/api/graphql",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload.get("data") or {}


def emit_shipments_dataset() -> None:
    emitter = DatahubRestEmitter(gms_server=GMS)
    now = int(time.time() * 1000)
    stamp = AuditStampClass(time=now, actor="urn:li:corpuser:premortem")
    fields = [
        ("shipment_id", "STRING"),
        ("order_id", "STRING"),
        ("order_status", "STRING"),
        ("carrier", "STRING"),
    ]
    schema_fields = [
        SchemaFieldClass(
            fieldPath=name,
            type=SchemaFieldDataTypeClass(type=StringTypeClass()),
            nativeDataType=native,
            description=f"Premortem demo field {name}",
            lastModified=stamp,
        )
        for name, native in fields
    ]
    schema = SchemaMetadataClass(
        schemaName="shipments",
        platform="urn:li:dataPlatform:snowflake",
        version=0,
        hash="",
        platformSchema=OtherSchemaClass(rawSchema="shipments(shipment_id,order_id,order_status,carrier)"),
        fields=schema_fields,
    )
    props = DatasetPropertiesClass(
        name="SHIPMENTS",
        description=(
            "Synthetic Premortem demo table — carries order_status so decoy and "
            "truly-ambiguous query beats resolve against a real catalog sibling."
        ),
    )
    for aspect in (props, schema):
        emitter.emit(
            MetadataChangeProposalWrapper(entityUrn=SHIPMENTS_URN, aspect=aspect)
        )
    emitter.flush()
    print(f"emitted dataset+schema {SHIPMENTS_URN}")


def update_lineage() -> None:
    edges = [
        {"upstreamUrn": DEMO_URN, "downstreamUrn": SHIPMENTS_URN},
        {"upstreamUrn": DEMO_URN, "downstreamUrn": ORDER_DETAILS_URN},
        {"upstreamUrn": DEMO_URN, "downstreamUrn": ORDER_DETAILS_REPLICA_URN},
    ]
    data = gql(
        """
        mutation($input: UpdateLineageInput!) {
          updateLineage(input: $input)
        }
        """,
        {"input": {"edgesToAdd": edges, "edgesToRemove": []}},
    )
    print(f"updateLineage → {data.get('updateLineage')}")


def rest_delete_entity(urn: str) -> None:
    """Hard-delete an entity (custom assertions are not deletable via GraphQL)."""
    body = json.dumps({"urn": urn}).encode("utf-8")
    req = urllib.request.Request(
        GMS + "/entities?action=delete",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def prune_probe_assertions() -> None:
    """Leave at most the stable camera assertion URN."""
    data = gql(
        """
        query($urn: String!) {
          dataset(urn: $urn) {
            assertions(start: 0, count: 50) { assertions { urn } }
          }
        }
        """,
        {"urn": DEMO_URN},
    )
    rows = (((data.get("dataset") or {}).get("assertions") or {}).get("assertions")) or []
    for row in rows:
        urn = row.get("urn")
        if not urn or urn == CAMERA_ASSERTION_URN:
            continue
        print(f"prune assertion {urn}")
        rest_delete_entity(urn)


def create_query(name: str, sql: str) -> str:
    # Idempotent: skip create when a query with this name already exists for DEMO_URN.
    client = create_catalog_client(
        backend="graphql", gms_url=GMS, write_back_enabled=False
    )
    existing = {q.query_id for q in client.get_dataset_queries(DEMO_URN)}
    if name in existing:
        print(f"createQuery skip (exists) {name}")
        return name

    data = gql(
        """
        mutation($input: CreateQueryInput!) {
          createQuery(input: $input) { urn }
        }
        """,
        {
            "input": {
                "properties": {
                    "name": name,
                    "description": f"Premortem demo beat: {name}",
                    "statement": {"value": sql, "language": "SQL"},
                },
                "subjects": [{"datasetUrn": DEMO_URN}],
            }
        },
    )
    urn = (data.get("createQuery") or {}).get("urn")
    print(f"createQuery {name} → {urn}")
    return str(urn)


def upsert_assertion() -> str:
    """Idempotent camera assertion — stable URN, upsert not append.

    OSS limitation: do not set fieldPath; assertionRunEvent rejects schemaField
    asserteeUrn. Column lives in description + result properties.
    """
    prune_probe_assertions()

    # Build product copy from a live rehearsal when possible.
    try:
        client = create_catalog_client(gms_url=GMS, write_back_enabled=False)
        diff = SchemaDiff(
            dataset_urn=DEMO_URN,
            kind="rename",
            column="order_status",
            new_column="order_state",
        )
        result = run_live_rehearsal(client, diff=diff, adjudicate=False)
        assertion = assertion_copy(result.forecast)
        assertion["external_url"] = FORECAST_URL
        description = assertion["description"]
        title_type = assertion["type"]
    except Exception as exc:  # noqa: BLE001
        print(f"assertion copy fallback ({exc})")
        description = (
            "Schema rehearsal: rename order_status → order_state. "
            "Premortem HARD/SOFT/UNKNOWN/CLEARED forecast. "
            "Column: order_status (dataset-scoped — OSS fieldPath limitation)."
        )
        title_type = "Premortem schema rehearsal"

    data = gql(
        """
        mutation($urn: String, $input: UpsertCustomAssertionInput!) {
          upsertCustomAssertion(urn: $urn, input: $input) { urn }
        }
        """,
        {
            "urn": CAMERA_ASSERTION_URN,
            "input": {
                "entityUrn": DEMO_URN,
                "type": title_type,
                "description": description,
                "platform": {"name": "premortem"},
                "logic": "premortem --live --rename order_status:order_state",
                "externalUrl": FORECAST_URL,
            },
        },
    )
    urn = ((data.get("upsertCustomAssertion") or {}).get("urn")) or CAMERA_ASSERTION_URN
    print(f"upsertCustomAssertion → {urn}")
    ASSERTION_URN_FILE.parent.mkdir(parents=True, exist_ok=True)
    ASSERTION_URN_FILE.write_text(urn + "\n", encoding="utf-8")

    # Wait until the assertion is readable before reporting a result.
    for _ in range(10):
        time.sleep(1)
        probe = gql(
            "query($urn: String!) { assertion(urn: $urn) { urn } }",
            {"urn": urn},
        )
        if (probe.get("assertion") or {}).get("urn"):
            break
    else:
        raise RuntimeError(f"assertion {urn} not readable after upsert")

    ok = gql(
        """
        mutation($urn: String!, $result: AssertionResultInput!) {
          reportAssertionResult(urn: $urn, result: $result)
        }
        """,
        {
            "urn": urn,
            "result": {
                "timestampMillis": int(time.time() * 1000),
                "type": "FAILURE",
                "externalUrl": FORECAST_URL,
                "properties": [
                    {"key": "source", "value": "premortem"},
                    {"key": "column", "value": "order_status"},
                ],
            },
        },
    )
    print(f"reportAssertionResult FAILURE → {ok.get('reportAssertionResult')}")

    # Guard: exactly one assertion on the demo dataset.
    listed = gql(
        """
        query($urn: String!) {
          dataset(urn: $urn) {
            assertions(start: 0, count: 50) { total assertions { urn } }
          }
        }
        """,
        {"urn": DEMO_URN},
    )
    total = (((listed.get("dataset") or {}).get("assertions") or {}).get("total")) or 0
    print(f"assertion count on demo dataset: {total}")
    if total != 1:
        raise RuntimeError(f"expected exactly 1 assertion on demo URN, got {total}")
    return str(urn)


def verify() -> int:
    client = create_catalog_client(gms_url=GMS, write_back_enabled=False)
    downstream = client.get_downstream(DEMO_URN)
    print(f"get_downstream count={len(downstream)}")
    for u in downstream:
        print(f"  - {u}")
    if len(downstream) < 2:
        print("FAIL: expected measured downstream > 1", file=sys.stderr)
        return 1

    diff = SchemaDiff(
        dataset_urn=DEMO_URN,
        kind="rename",
        column="order_status",
        new_column="order_state",
    )
    result = run_live_rehearsal(client, diff=diff, adjudicate=False)
    by_id = {f.query_id: f.severity for f in result.forecast.findings}
    print(f"live queries={result.query_count} tables={list((result.tables or {}).keys())}")
    print(result.markdown)

    # Both video beats must be visible artifacts in the markdown report.
    if "CLEARED" not in result.markdown or "binds to `shipments`" not in result.markdown:
        print("FAIL: cleared decoy row missing from report", file=sys.stderr)
        return 1
    if "unknown_bare_two_tables" not in result.markdown:
        print("FAIL: honest UNKNOWN row missing from report", file=sys.stderr)
        return 1

    from premortem.classify import classify_query

    tables = result.tables or {}
    decoy = classify_query(
        DECOY_SQL,
        column="order_status",
        dialect="snowflake",
        subject_table="order_history",
        tables=tables,
    )
    amb = classify_query(
        AMBIGUOUS_SQL,
        column="order_status",
        dialect="snowflake",
        subject_table="order_history",
        tables=tables,
    )
    print(f"decoy → {decoy.severity.value} evidence={decoy.evidence}")
    print(f"ambiguous → {amb.severity.value}")
    if decoy.severity is not BreakSeverity.UNAFFECTED:
        print("FAIL: decoy beat", file=sys.stderr)
        return 1
    if not decoy.evidence.startswith("BOUND_ELSEWHERE:"):
        print("FAIL: decoy missing BOUND_ELSEWHERE evidence", file=sys.stderr)
        return 1
    if amb.severity is not BreakSeverity.UNKNOWN:
        print("FAIL: ambiguous beat", file=sys.stderr)
        return 1
    # Ensure both appear in the live forecast corpus (queries present)
    sqls = " ".join(q.sql.lower() for q in client.get_dataset_queries(DEMO_URN))
    if "from shipments s where s.order_status" not in " ".join(sqls.split()):
        # looser check
        if DECOY_SQL.lower() not in sqls and "s.order_status" not in sqls:
            print("FAIL: decoy query not in catalog listQueries", file=sys.stderr)
            return 1
    if "join shipments" not in sqls:
        print("FAIL: ambiguous query not in catalog listQueries", file=sys.stderr)
        return 1
    print("VERIFY OK — both video beats resolvable; downstream > 1")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--skip-assertion", action="store_true")
    args = ap.parse_args()
    if not args.verify_only:
        emit_shipments_dataset()
        update_lineage()
        create_query("decoy_shipments_order_status", DECOY_SQL)
        create_query("unknown_bare_two_tables", AMBIGUOUS_SQL)
        if not args.skip_assertion:
            upsert_assertion()
        # Give search/listQueries a moment to index
        time.sleep(2)
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
