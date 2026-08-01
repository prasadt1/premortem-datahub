"""GraphQL HTTP catalog backend — current default DataHub access path."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from premortem.catalog.protocol import GraphqlError, WriteBackDisabledError
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


class GraphqlCatalogClient:
    """GraphQL HTTP client implementing CatalogClient.

    Write methods (Gate 1 PASS): ``add_tags``, ``update_description``,
    and ``save_forecast_document`` (createDocument when available, else
    description append).

    Read methods (Gate 2): schema, lineage, queries. Prefers indexed
    ``listQueries`` when present; falls back to ``examples/seeded_queries.json``.
    Results are deduped by normalized SQL (query logs and re-seeds repeat).
    """

    def __init__(
        self,
        *,
        gms_url: str | None = None,
        token: str | None = None,
        write_back_enabled: bool = True,
        seed_path: str | None = None,
    ) -> None:
        self.gms_url = (gms_url or os.environ.get("DATAHUB_GMS_URL") or DEFAULT_GMS).rstrip(
            "/"
        )
        self.token = token or os.environ.get("DATAHUB_GMS_TOKEN") or os.environ.get(
            "DATAHUB_TOKEN"
        )
        self.write_back_enabled = write_back_enabled
        self.seed_path = Path(seed_path) if seed_path else _default_seed_path()

    def _post(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.gms_url + "/api/graphql"
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise GraphqlError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise GraphqlError(f"Cannot reach {url}: {e.reason}") from e
        if payload.get("errors"):
            raise GraphqlError(json.dumps(payload["errors"], indent=2))
        return payload.get("data") or {}

    def _require_write_back(self) -> None:
        if not self.write_back_enabled:
            raise WriteBackDisabledError(
                "Write-back disabled (set write_back_enabled=True after Gate 1 PASS)"
            )

    def list_schema_fields(self, urn: str) -> list[str]:
        data = self._post(
            """
            query($urn: String!) {
              dataset(urn: $urn) {
                schemaMetadata { fields { fieldPath } }
              }
            }
            """,
            {"urn": urn},
        )
        fields = (((data.get("dataset") or {}).get("schemaMetadata") or {}).get("fields")) or []
        return [f["fieldPath"] for f in fields if f.get("fieldPath")]

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]:
        data = self._post(
            """
            query($urn: String!) {
              dataset(urn: $urn) {
                relationships(
                  input: { types: ["DownstreamOf"], direction: INCOMING, start: 0, count: 100 }
                ) {
                  relationships { entity { urn } }
                }
              }
            }
            """,
            {"urn": urn},
        )
        rels = (
            ((data.get("dataset") or {}).get("relationships") or {}).get("relationships")
        ) or []
        out = []
        for rel in rels:
            entity = rel.get("entity") or {}
            if entity.get("urn"):
                out.append(entity["urn"])
        # Self-edges (dataset listed as its own DownstreamOf) are not dependents.
        return filter_self_urn(urn, out)

    def search_datasets(self, query: str, *, limit: int = 20) -> list[str]:
        data = self._post(
            """
            query($q: String!, $count: Int!) {
              search(input: { type: DATASET, query: $q, start: 0, count: $count }) {
                searchResults { entity { urn } }
              }
            }
            """,
            {"q": query, "count": limit},
        )
        rows = ((data.get("search") or {}).get("searchResults")) or []
        out: list[str] = []
        for row in rows:
            entity = row.get("entity") or {}
            if entity.get("urn"):
                out.append(entity["urn"])
        return out

    def get_owners(self, urn: str) -> list[str]:
        """CorpUser / CorpGroup URNs from Ownership aspect; empty if none recorded."""
        data = self._post(
            """
            query($urn: String!) {
              dataset(urn: $urn) {
                ownership {
                  owners {
                    owner {
                      ... on CorpUser { urn }
                      ... on CorpGroup { urn }
                    }
                  }
                }
              }
            }
            """,
            {"urn": urn},
        )
        owners = (((data.get("dataset") or {}).get("ownership") or {}).get("owners")) or []
        out: list[str] = []
        for row in owners:
            owner = (row or {}).get("owner") or {}
            u = owner.get("urn")
            if u:
                out.append(u)
        return out

    def get_description(self, urn: str) -> str:
        """Editable properties description when present; else empty string."""
        data = self._post(
            """
            query($urn: String!) {
              dataset(urn: $urn) {
                editableProperties { description }
                properties { description }
              }
            }
            """,
            {"urn": urn},
        )
        ds = data.get("dataset") or {}
        editable = ((ds.get("editableProperties") or {}).get("description")) or ""
        if editable:
            return str(editable)
        props = ((ds.get("properties") or {}).get("description")) or ""
        return str(props)

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:
        # Prefer catalog listQueries when indexed; seed is fallback / PREMORTEM_PREFER_SEED.
        if self._force_seed():
            return dedupe_queries_by_sql(self._queries_from_seed(urn))

        try:
            data = self._post(
                """
                query($urn: String!) {
                  listQueries(input: { start: 0, count: 100, datasetUrn: $urn }) {
                    total
                    queries {
                      urn
                      properties { name statement { value } }
                    }
                  }
                }
                """,
                {"urn": urn},
            )
            rows = ((data.get("listQueries") or {}).get("queries")) or []
            if rows:
                records: list[QueryRecord] = []
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
                if records:
                    return dedupe_queries_by_sql(records)
        except GraphqlError:
            pass

        return dedupe_queries_by_sql(self._queries_from_seed(urn))

    def _force_seed(self) -> bool:
        return os.environ.get("PREMORTEM_PREFER_SEED", "").lower() in {"1", "true", "yes"}

    def _queries_from_seed(self, urn: str) -> list[QueryRecord]:
        if not self.seed_path or not self.seed_path.is_file():
            return []
        payload = json.loads(self.seed_path.read_text(encoding="utf-8"))
        if payload.get("dataset_urn") != urn:
            return []
        records: list[QueryRecord] = []
        for q in payload.get("queries") or []:
            sql = q.get("sql")
            query_urn = q.get("query_urn")
            if query_urn:
                try:
                    data = self._post(
                        """
                        query($urn: String!) {
                          entity(urn: $urn) {
                            ... on QueryEntity {
                              properties { name statement { value } }
                            }
                          }
                        }
                        """,
                        {"urn": query_urn},
                    )
                    props = ((data.get("entity") or {}).get("properties")) or {}
                    live_sql = ((props.get("statement") or {}).get("value")) or sql
                    name = props.get("name") or q.get("query_id")
                    if live_sql:
                        records.append(
                            QueryRecord(
                                query_id=name,
                                sql=live_sql,
                                dataset_urn=urn,
                                exec_count=q.get("exec_count"),
                            )
                        )
                        continue
                except GraphqlError:
                    pass
            if sql:
                records.append(
                    QueryRecord(
                        query_id=q.get("query_id") or "query",
                        sql=sql,
                        dataset_urn=urn,
                        exec_count=q.get("exec_count"),
                    )
                )
        return records

    def ensure_forecast_tag(self) -> str:
        """Create Premortem forecast tag if missing; return its URN."""
        self._require_write_back()
        try:
            self._post(
                """
                mutation CreateForecastTag($input: CreateTagInput!) {
                  createTag(input: $input)
                }
                """,
                {
                    "input": {
                        "id": FORECAST_TAG_ID,
                        "name": "Premortem Forecast",
                        "description": "Schema-change rehearsal forecast written by Premortem",
                    }
                },
            )
        except GraphqlError:
            pass  # already exists
        return FORECAST_TAG_URN

    def add_tags(self, urn: str, tag_urns: list[str]) -> None:
        self._require_write_back()
        self._post(
            """
            mutation PremortemAddTags($input: BatchAddTagsInput!) {
              batchAddTags(input: $input)
            }
            """,
            {
                "input": {
                    "tagUrns": tag_urns,
                    "resources": [{"resourceUrn": urn}],
                }
            },
        )

    def update_description(self, urn: str, description: str) -> None:
        self._require_write_back()
        self._post(
            """
            mutation PremortemUpdateDesc($input: DescriptionUpdateInput!) {
              updateDescription(input: $input)
            }
            """,
            {"input": {"description": description, "resourceUrn": urn}},
        )

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str:
        """Write forecast so it is visible on the dataset page.

        Quickstart often creates Document entities that never appear in search.
        Always also tag + update the dataset description (Gate 1–proven, UI-visible).
        Still attempt createDocument for Cloud / newer stacks.
        """
        self._require_write_back()
        refs: list[str] = []

        try:
            data = self._post(
                """
                mutation PremortemCreateDoc($input: CreateDocumentInput!) {
                  createDocument(input: $input)
                }
                """,
                {
                    "input": {
                        "title": title,
                        "contents": {"text": body_md},
                        "relatedAssets": [urn],
                    }
                },
            )
            doc = data.get("createDocument")
            if isinstance(doc, str) and doc:
                refs.append(doc)
            elif isinstance(doc, dict) and doc.get("urn"):
                refs.append(str(doc["urn"]))
        except GraphqlError:
            pass

        tag = self.ensure_forecast_tag()
        self.add_tags(urn, [tag])
        from premortem.description_merge import (
            forecast_description_section,
            merge_premortem_description,
        )

        section = forecast_description_section(title=title, body_md=body_md)
        merged = merge_premortem_description(self.get_description(urn), section)
        self.update_description(urn, merged)
        refs.append(f"description+tag:{tag}")
        return " | ".join(refs)


# Backward-compatible alias
HttpDataHubClient = GraphqlCatalogClient
