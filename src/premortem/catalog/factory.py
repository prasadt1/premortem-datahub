"""Factory for catalog backends — Kit default; GraphQL explicit fallback."""

from __future__ import annotations

import os
from typing import Any

from premortem.catalog.fake import FakeCatalogClient
from premortem.catalog.graphql import GraphqlCatalogClient
from premortem.catalog.kit import KitCatalogClient
from premortem.catalog.protocol import CatalogClient

BACKENDS = frozenset({"graphql", "kit", "fake"})


def _resolve_backend_name(backend: str | None) -> str:
    """Prefer PREMORTEM_CATALOG, then PREMORTEM_CATALOG_BACKEND, default kit."""
    if backend:
        return backend.lower()
    for key in ("PREMORTEM_CATALOG", "PREMORTEM_CATALOG_BACKEND"):
        val = os.environ.get(key)
        if val:
            return val.lower()
    return "kit"


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
    2. ``PREMORTEM_CATALOG`` or ``PREMORTEM_CATALOG_BACKEND`` env
    3. Default ``kit`` (stage-1 surface). Use ``graphql`` as explicit fallback.
    """
    name = _resolve_backend_name(backend)
    if name not in BACKENDS:
        raise ValueError(
            f"Unknown catalog backend {name!r}; expected one of {sorted(BACKENDS)}"
        )
    if name == "fake":
        return fake if fake is not None else FakeCatalogClient(
            write_back_enabled=write_back_enabled
        )
    if name == "kit":
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
