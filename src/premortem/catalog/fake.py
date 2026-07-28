"""In-memory catalog client for unit tests (no network)."""

from __future__ import annotations

from premortem.catalog.protocol import WriteBackDisabledError
from premortem.catalog.queries import dedupe_queries_by_sql, filter_self_urn
from premortem.models import QueryRecord


class FakeCatalogClient:
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
        return filter_self_urn(urn, list(self.downstream))

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:
        return dedupe_queries_by_sql([q.model_copy() for q in self.queries])

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


# Backward-compatible alias
FakeDataHubClient = FakeCatalogClient
