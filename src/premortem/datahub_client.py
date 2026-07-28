"""Backward-compatible re-exports — prefer ``premortem.catalog``.

Existing imports (``from premortem.datahub_client import …``) keep working.
New code should use ``premortem.catalog.create_catalog_client``.
"""

from __future__ import annotations

from premortem.catalog import (
    DEFAULT_GMS,
    FORECAST_TAG_ID,
    FORECAST_TAG_URN,
    CatalogClient,
    DataHubClient,
    FakeDataHubClient,
    GraphqlError,
    HttpDataHubClient,
    KitBackendNotReady,
    WriteBackDisabledError,
    create_catalog_client,
    write_forecast_to_catalog,
)

__all__ = [
    "DEFAULT_GMS",
    "FORECAST_TAG_ID",
    "FORECAST_TAG_URN",
    "CatalogClient",
    "DataHubClient",
    "FakeDataHubClient",
    "GraphqlError",
    "HttpDataHubClient",
    "KitBackendNotReady",
    "WriteBackDisabledError",
    "create_catalog_client",
    "write_forecast_to_catalog",
]
