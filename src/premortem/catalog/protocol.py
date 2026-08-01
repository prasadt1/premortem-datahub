"""Catalog access-layer protocol — backend-agnostic DataHub surface.

Callers (live rehearsal, CLI, future Premortem MCP) depend on this Protocol only.
Implementations: GraphQL HTTP (default), Fake (tests), Kit SDK (post S1/S3).
"""

from __future__ import annotations

from typing import Protocol

from premortem.models import QueryRecord


class WriteBackDisabledError(RuntimeError):
    """Raised when a write method is called with write_back_enabled=False."""


class CatalogError(RuntimeError):
    """Backend-agnostic catalog failure (GraphQL, Kit, or network)."""


class GraphqlError(CatalogError):
    """GraphQL transport / schema error (legacy name kept for callers)."""


class CatalogClient(Protocol):
    """Access-layer interface for schema, lineage, query history, and write-back."""

    def list_schema_fields(self, urn: str) -> list[str]: ...

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]: ...

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]: ...

    def search_datasets(self, query: str, *, limit: int = 20) -> list[str]:
        """Return dataset URNs matching ``query`` (name / keyword search)."""
        ...

    def get_owners(self, urn: str) -> list[str]:
        """Return corpuser / corpGroup URNs owning ``urn`` (empty if none recorded)."""
        ...

    def get_description(self, urn: str) -> str:
        """Return the dataset's editable/properties description (empty if none)."""
        ...

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str: ...

    def add_tags(self, urn: str, tag_urns: list[str]) -> None: ...

    def update_description(self, urn: str, description: str) -> None: ...


# Backward-compatible alias used throughout the existing codebase.
DataHubClient = CatalogClient
