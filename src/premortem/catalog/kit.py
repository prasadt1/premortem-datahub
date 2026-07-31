"""DataHub Agent Kit SDK catalog backend (stage-1 surface).

Wraps ``datahub-agent-context`` tools (list_schema_fields, get_lineage,
get_dataset_queries, search, add_tags, update_description) behind
CatalogClient. Default for ``--live`` after S3 green.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from premortem.catalog.protocol import CatalogError, WriteBackDisabledError
from premortem.catalog.queries import dedupe_queries_by_sql, filter_self_urn
from premortem.models import QueryRecord

DEFAULT_GMS = "http://localhost:8080"
FORECAST_TAG_ID = "premortem_forecast"
FORECAST_TAG_URN = f"urn:li:tag:{FORECAST_TAG_ID}"


def _default_seed_path() -> Path | None:
    env = os.environ.get("PREMORTEM_SEEDED_QUERIES")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidate = here.parents[3] / "examples" / "seeded_queries.json"
    return candidate if candidate.is_file() else None


class KitCatalogClient:
    """CatalogClient via DataHub Agent Context Kit tools."""

    def __init__(
        self,
        *,
        gms_url: str | None = None,
        token: str | None = None,
        write_back_enabled: bool = True,
        seed_path: str | None = None,
    ) -> None:
        try:
            from datahub.sdk.main_client import DataHubClient
            from datahub_agent_context.context import DataHubContext, set_client
        except ImportError as exc:  # pragma: no cover
            raise CatalogError(
                "datahub-agent-context is required for the Kit backend. "
                "pip install 'datahub-agent-context' or set "
                "PREMORTEM_CATALOG=graphql"
            ) from exc

        self.gms_url = (gms_url or os.environ.get("DATAHUB_GMS_URL") or DEFAULT_GMS).rstrip(
            "/"
        )
        self.token = token or os.environ.get("DATAHUB_GMS_TOKEN") or os.environ.get(
            "DATAHUB_TOKEN"
        )
        self.write_back_enabled = write_back_enabled
        self.seed_path = Path(seed_path) if seed_path else _default_seed_path()
        kwargs: dict[str, Any] = {"server": self.gms_url}
        if self.token:
            kwargs["token"] = self.token
        self._client = DataHubClient(**kwargs)
        self._DataHubContext = DataHubContext
        self._set_client = set_client
        # Keep client in context for the lifetime of this adapter (tools read
        # contextvars). Tests / concurrent use should create separate instances.
        self._ctx_token = set_client(self._client)

    def _require_write_back(self) -> None:
        if not self.write_back_enabled:
            raise WriteBackDisabledError(
                "Write-back disabled (set write_back_enabled=True after Gate 1 PASS)"
            )

    def list_schema_fields(self, urn: str) -> list[str]:
        from datahub_agent_context.mcp_tools.entities import list_schema_fields

        with self._DataHubContext(self._client):
            payload = list_schema_fields(urn)
        fields = (payload or {}).get("fields") or []
        return [f["fieldPath"] for f in fields if isinstance(f, dict) and f.get("fieldPath")]

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]:
        from datahub_agent_context.mcp_tools.lineage import get_lineage

        with self._DataHubContext(self._client):
            payload = get_lineage(
                urn, column=column, upstream=False, max_hops=1, max_results=100
            )
        rows = ((payload or {}).get("downstreams") or {}).get("searchResults") or []
        out: list[str] = []
        for row in rows:
            entity = row.get("entity") or {}
            if entity.get("urn"):
                out.append(entity["urn"])
        return filter_self_urn(urn, out)

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:
        if os.environ.get("PREMORTEM_PREFER_SEED", "").lower() in {"1", "true", "yes"}:
            return dedupe_queries_by_sql(self._queries_from_seed(urn))

        from datahub_agent_context.mcp_tools.queries import get_dataset_queries

        records: list[QueryRecord] = []
        try:
            with self._DataHubContext(self._client):
                # Paginate — Kit default count is small.
                start = 0
                page = 50
                while True:
                    payload = get_dataset_queries(urn, start=start, count=page)
                    rows = (payload or {}).get("queries") or []
                    for q in rows:
                        props = q.get("properties") or {}
                        sql = ((props.get("statement") or {}).get("value")) or ""
                        if not sql:
                            continue
                        records.append(
                            QueryRecord(
                                query_id=props.get("name") or q.get("urn") or "query",
                                sql=sql,
                                dataset_urn=urn,
                                exec_count=None,
                            )
                        )
                    total = int((payload or {}).get("total") or 0)
                    start += len(rows)
                    if not rows or start >= total:
                        break
        except Exception as exc:  # noqa: BLE001 — fall back to seed
            if not records:
                # Prefer seed when Kit/query index fails
                seeded = self._queries_from_seed(urn)
                if seeded:
                    return dedupe_queries_by_sql(seeded)
                raise CatalogError(f"Kit get_dataset_queries failed: {exc}") from exc

        if records:
            return dedupe_queries_by_sql(records)
        return dedupe_queries_by_sql(self._queries_from_seed(urn))

    def _queries_from_seed(self, urn: str) -> list[QueryRecord]:
        if not self.seed_path or not self.seed_path.is_file():
            return []
        payload = json.loads(self.seed_path.read_text(encoding="utf-8"))
        if payload.get("dataset_urn") != urn:
            return []
        out: list[QueryRecord] = []
        for q in payload.get("queries") or []:
            sql = q.get("sql")
            if not sql:
                continue
            out.append(
                QueryRecord(
                    query_id=q.get("query_id") or "query",
                    sql=sql,
                    dataset_urn=urn,
                    exec_count=q.get("exec_count"),
                )
            )
        return out

    def search_datasets(self, query: str, *, limit: int = 20) -> list[str]:
        from datahub_agent_context.mcp_tools.search import search

        with self._DataHubContext(self._client):
            # Kit search prefers /q queries; keep plain keywords for table names.
            payload = search(query=query, filter="type = 'dataset'", num_results=limit)
        # Response shape varies; accept searchResults or results
        rows = (
            (payload or {}).get("searchResults")
            or (payload or {}).get("results")
            or []
        )
        if isinstance(payload, dict) and "entities" in payload:
            rows = payload["entities"]
        out: list[str] = []
        for row in rows:
            if isinstance(row, str) and row.startswith("urn:"):
                out.append(row)
                continue
            entity = row.get("entity") if isinstance(row, dict) else None
            if isinstance(entity, dict) and entity.get("urn"):
                out.append(entity["urn"])
            elif isinstance(row, dict) and row.get("urn"):
                out.append(row["urn"])
        return out

    def get_owners(self, urn: str) -> list[str]:
        """Ownership is not a first-class Kit read — GraphQL fallback."""
        from premortem.catalog.graphql import GraphqlCatalogClient

        gql = GraphqlCatalogClient(
            gms_url=self.gms_url,
            token=self.token,
            write_back_enabled=False,
            seed_path=str(self.seed_path) if self.seed_path else None,
        )
        return gql.get_owners(urn)

    def get_description(self, urn: str) -> str:
        from premortem.catalog.graphql import GraphqlCatalogClient

        gql = GraphqlCatalogClient(
            gms_url=self.gms_url,
            token=self.token,
            write_back_enabled=False,
            seed_path=str(self.seed_path) if self.seed_path else None,
        )
        return gql.get_description(urn)

    def ensure_forecast_tag(self) -> str:
        """Best-effort create of the Premortem forecast tag; return URN."""
        self._require_write_back()
        # Tag creation is not a first-class Kit mutation on all stacks — GraphQL.
        from premortem.catalog.graphql import GraphqlCatalogClient

        gql = GraphqlCatalogClient(
            gms_url=self.gms_url,
            token=self.token,
            write_back_enabled=True,
            seed_path=str(self.seed_path) if self.seed_path else None,
        )
        return gql.ensure_forecast_tag()

    def add_tags(self, urn: str, tag_urns: list[str]) -> None:
        self._require_write_back()
        from datahub_agent_context.mcp_tools.tags import add_tags

        with self._DataHubContext(self._client):
            add_tags(tag_urns=tag_urns, entity_urns=[urn])

    def update_description(self, urn: str, description: str) -> None:
        self._require_write_back()
        from datahub_agent_context.mcp_tools.descriptions import update_description

        with self._DataHubContext(self._client):
            update_description(
                entity_urn=urn, operation="replace", description=description
            )

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str:
        """Tag + description write-back (assertion applied via write_payload / host)."""
        self._require_write_back()
        tag = self.ensure_forecast_tag()
        self.add_tags(urn, [tag])
        from premortem.description_merge import merge_premortem_description

        section = (
            f"## {title}\n\n{body_md.rstrip()}\n\n"
            "---\n_Premortem schema rehearsal "
            "(hard / soft / unknown / cleared). Tag: premortem_forecast._"
        )
        merged = merge_premortem_description(self.get_description(urn), section)
        self.update_description(urn, merged)
        return f"description+tag:{tag}"
