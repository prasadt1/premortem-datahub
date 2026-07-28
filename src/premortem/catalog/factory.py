"""Factory for catalog backends — GraphQL default; Kit is a post-spike swap."""

from __future__ import annotations

import os
from typing import Any

from premortem.catalog.fake import FakeCatalogClient
from premortem.catalog.graphql import GraphqlCatalogClient
from premortem.catalog.kit import KitCatalogClient
from premortem.catalog.protocol import CatalogClient

BACKENDS = frozenset({"graphql", "kit", "fake"})


def create_catalog_client(
    *,
    backend: str | None = None,
    gms_url: str | None = None,
    token: str | None = None,
    write_back_enabled: bool = True,
    seed_path: str | None = None,
    fake: FakeCatalogClient | None = None,
    **_unused: Any,
) -> CatalogClient:
    """Return a CatalogClient.

    Backend selection (first match wins):
    1. Explicit ``backend=`` argument
    2. ``PREMORTEM_CATALOG_BACKEND`` env (graphql | kit | fake)
    3. Default ``graphql``

    ``kit`` raises ``KitBackendNotReady`` until spikes S1–S3 land and the SDK
    adapter is filled in — intentional fail-fast so stage-1 cannot silently
    depend on an empty shell.
    """
    name = (backend or os.environ.get("PREMORTEM_CATALOG_BACKEND") or "graphql").lower()
    if name not in BACKENDS:
        raise ValueError(
            f"Unknown catalog backend {name!r}; expected one of {sorted(BACKENDS)}"
        )
    if name == "fake":
        return fake if fake is not None else FakeCatalogClient(
            write_back_enabled=write_back_enabled
        )
    if name == "kit":
        # Constructor raises KitBackendNotReady until wired.
        return KitCatalogClient(
            gms_url=gms_url,
            token=token,
            write_back_enabled=write_back_enabled,
            seed_path=seed_path,
        )
    return GraphqlCatalogClient(
        gms_url=gms_url,
        token=token,
        write_back_enabled=write_back_enabled,
        seed_path=seed_path,
    )


__all__ = [
    "BACKENDS",
    "create_catalog_client",
]
