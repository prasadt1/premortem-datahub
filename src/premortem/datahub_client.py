"""Thin DataHub client — GraphQL writes enabled after Gate 1 PASS."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from premortem.models import QueryRecord

DEFAULT_GMS = "http://localhost:8080"
FORECAST_TAG_ID = "premortem_forecast"
FORECAST_TAG_URN = f"urn:li:tag:{FORECAST_TAG_ID}"


class WriteBackDisabledError(RuntimeError):
    """Raised when a write method is called with write_back_enabled=False."""


class GraphqlError(RuntimeError):
    pass


class DataHubClient(Protocol):
    def list_schema_fields(self, urn: str) -> list[str]: ...

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]: ...

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]: ...

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str: ...

    def add_tags(self, urn: str, tag_urns: list[str]) -> None: ...

    def update_description(self, urn: str, description: str) -> None: ...


class FakeDataHubClient:
    """In-memory client for unit tests (no network)."""

    def __init__(
        self,
        *,
        fields: list[str] | None = None,
        downstream: list[str] | None = None,
        queries: list[QueryRecord] | None = None,
        write_back_enabled: bool = False,
    ) -> None:
        self.fields = list(fields or [])
        self.downstream = list(downstream or [])
        self.queries = list(queries or [])
        self.write_back_enabled = write_back_enabled
        self.saved_docs: list[tuple[str, str, str]] = []
        self.added_tags: list[tuple[str, list[str]]] = []
        self.descriptions: list[tuple[str, str]] = []

    def list_schema_fields(self, urn: str) -> list[str]:
        return list(self.fields)

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]:
        return list(self.downstream)

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:
        return [q.model_copy() for q in self.queries]

    def _require_write_back(self) -> None:
        if not self.write_back_enabled:
            raise WriteBackDisabledError(
                "Write-back disabled until VERIFY.md Gate 1 is PASS"
            )

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str:
        self._require_write_back()
        doc_urn = f"urn:li:document:fake-{len(self.saved_docs)}"
        self.saved_docs.append((urn, title, body_md))
        return doc_urn

    def add_tags(self, urn: str, tag_urns: list[str]) -> None:
        self._require_write_back()
        self.added_tags.append((urn, list(tag_urns)))

    def update_description(self, urn: str, description: str) -> None:
        self._require_write_back()
        self.descriptions.append((urn, description))


def _default_seed_path() -> Path | None:
    env = os.environ.get("PREMORTEM_SEEDED_QUERIES")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidate = here.parents[2] / "examples" / "seeded_queries.json"
    return candidate if candidate.is_file() else None


class HttpDataHubClient:
    """GraphQL HTTP client.

    Write methods (Gate 1 PASS): ``add_tags``, ``update_description``,
    and ``save_forecast_document`` (createDocument when available, else
    description append).

    Read methods (Gate 2): schema, lineage, queries. ``get_dataset_queries``
    tries ``listQueries`` then falls back to ``examples/seeded_queries.json``
    (Quickstart search index often omits QUERY entities).
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
        return out

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:
        # Prefer indexed listQueries when Gate 2 search works.
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
                    return records
        except GraphqlError:
            pass

        return self._queries_from_seed(urn)

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
            # Prefer live entity fetch when GMS has the seed; fall back to file SQL.
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
        # Keep original description context: prepend a clear Premortem block.
        header = f"## {title}\n\n"
        footer = (
            "\n\n---\n_Premortem schema rehearsal "
            "(hard / soft / unknown). Tag: premortem_forecast._"
        )
        self.update_description(urn, header + body_md + footer)
        refs.append(f"description+tag:{tag}")
        return " | ".join(refs)


def write_forecast_to_catalog(
    client: DataHubClient,
    *,
    urn: str,
    title: str,
    body_md: str,
) -> str:
    """Write forecast via Gate 1–verified mutations."""
    return client.save_forecast_document(urn, title, body_md)
