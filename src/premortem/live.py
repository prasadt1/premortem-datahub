"""Live DataHub rehearsal orchestration (schema + queries + optional write-back)."""

from __future__ import annotations

from dataclasses import dataclass

from premortem.agent import rehearse
from premortem.catalog import CatalogClient, write_forecast_to_catalog
from premortem.models import Forecast, SchemaDiff
from premortem.report import to_json, to_markdown


def _subject_table_from_urn(urn: str) -> str | None:
    """Best-effort dataset base name from a DataHub dataset URN."""
    # urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91....order_history,PROD)
    if "," in urn:
        mid = urn.split(",", 1)[1]
        name = mid.rsplit(",", 1)[0].strip()
        if name:
            return name.split(".")[-1]
    return None


@dataclass
class LiveRehearsalResult:
    forecast: Forecast
    markdown: str
    json_text: str
    schema_fields: list[str]
    downstream: list[str]
    query_count: int
    write_back_ref: str | None = None


def run_live_rehearsal(
    client: CatalogClient,
    *,
    diff: SchemaDiff,
    dialect: str = "snowflake",
    use_exec_count: bool = False,
    adjudicate: bool = False,
    write_back: bool = False,
    lineage_count_override: int | None = None,
) -> LiveRehearsalResult:
    """Fetch schema/lineage/queries from DataHub and build a forecast."""
    fields = client.list_schema_fields(diff.dataset_urn)
    if not fields:
        raise RuntimeError(f"no schema fields for {diff.dataset_urn}")
    if diff.column not in {f.split(".")[-1] for f in fields} and diff.column not in fields:
        # allow fieldPath or bare name
        bare = {f.split(".")[-1].lower() for f in fields}
        if diff.column.lower() not in bare and diff.column not in fields:
            raise RuntimeError(
                f"column `{diff.column}` not in schema for {diff.dataset_urn}; "
                f"fields={fields}"
            )

    downstream = client.get_downstream(diff.dataset_urn)
    queries = client.get_dataset_queries(diff.dataset_urn)
    if not queries:
        raise RuntimeError(
            f"no queries for {diff.dataset_urn} "
            "(listQueries empty and seed file missing/mismatched)"
        )

    lineage_count = (
        lineage_count_override
        if lineage_count_override is not None
        else len(downstream)
    )
    # Prefer bare field names for adjudication
    schema_for_agent = sorted({f.split(".")[-1] for f in fields})
    subject_table = _subject_table_from_urn(diff.dataset_urn)
    tables = {subject_table: schema_for_agent} if subject_table else None

    forecast = rehearse(
        diff=diff,
        queries=queries,
        lineage_dependent_count=lineage_count,
        dialect=dialect,
        use_exec_count=use_exec_count,
        schema_fields=schema_for_agent,
        lineage_neighbors=downstream,
        adjudicate=adjudicate,
        subject_table=subject_table,
        tables=tables,
    )
    md = to_markdown(forecast, use_exec_count=use_exec_count)
    js = to_json(forecast, use_exec_count=use_exec_count)

    ref = None
    if write_back:
        title = f"Premortem: {diff.kind} {diff.column}"
        ref = write_forecast_to_catalog(
            client, urn=diff.dataset_urn, title=title, body_md=md
        )

    return LiveRehearsalResult(
        forecast=forecast,
        markdown=md,
        json_text=js,
        schema_fields=schema_for_agent,
        downstream=downstream,
        query_count=len(queries),
        write_back_ref=ref,
    )
