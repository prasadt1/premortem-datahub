"""Catalog access layer — Protocol + pluggable backends.

Default backend is raw GraphQL (``GraphqlCatalogClient``). The DataHub Agent
Kit SDK lands behind the same Protocol after spikes S1–S3; Premortem MCP should
not be started until this facade is stable.
"""

from __future__ import annotations

from premortem.catalog.factory import BACKENDS, create_catalog_client
from premortem.catalog.fake import FakeCatalogClient, FakeDataHubClient
from premortem.catalog.graphql import (
    DEFAULT_GMS,
    FORECAST_TAG_ID,
    FORECAST_TAG_URN,
    GraphqlCatalogClient,
    HttpDataHubClient,
)
from premortem.catalog.kit import KitCatalogClient
from premortem.catalog.protocol import (
    CatalogClient,
    CatalogError,
    DataHubClient,
    GraphqlError,
    KitBackendNotReady,
    WriteBackDisabledError,
)
from premortem.catalog.queries import dedupe_queries_by_sql, filter_self_urn, normalize_sql


def write_forecast_to_catalog(
    client: CatalogClient,
    *,
    urn: str,
    title: str,
    body_md: str,
) -> str:
    """Write forecast via Gate 1–verified mutations."""
    return client.save_forecast_document(urn, title, body_md)


__all__ = [
    "BACKENDS",
    "CatalogClient",
    "CatalogError",
    "DEFAULT_GMS",
    "DataHubClient",
    "FORECAST_TAG_ID",
    "FORECAST_TAG_URN",
    "FakeCatalogClient",
    "FakeDataHubClient",
    "GraphqlCatalogClient",
    "GraphqlError",
    "HttpDataHubClient",
    "KitBackendNotReady",
    "KitCatalogClient",
    "WriteBackDisabledError",
    "create_catalog_client",
    "dedupe_queries_by_sql",
    "filter_self_urn",
    "normalize_sql",
    "write_forecast_to_catalog",
]
