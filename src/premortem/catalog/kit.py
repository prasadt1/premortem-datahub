"""DataHub Agent Kit SDK catalog backend — interface reserved for post-spike swap.

Spikes S1–S3 decide whether the Kit can satisfy stage-1 assertions and which
write surface to use. Until those land, selecting ``backend=kit`` fails fast
with a clear error. Call sites that go through ``create_catalog_client`` need
no rewrite when the Kit implementation is filled in.
"""

from __future__ import annotations

from premortem.catalog.protocol import KitBackendNotReady
from premortem.models import QueryRecord


class KitCatalogClient:
    """CatalogClient implemented via the DataHub Agent Kit SDK.

    Construction succeeds only after ``PREMORTEM_KIT_READY=1`` *and* a real
    SDK adapter is wired (post S1/S3). Until then, ``create_catalog_client``
    refuses this backend so misconfiguration cannot silently fall back.
    """

    def __init__(
        self,
        *,
        gms_url: str | None = None,
        token: str | None = None,
        write_back_enabled: bool = True,
        seed_path: str | None = None,
    ) -> None:
        raise KitBackendNotReady(
            "Kit SDK catalog backend is not wired yet (await spikes S1–S3). "
            "Use PREMORTEM_CATALOG_BACKEND=graphql (default) or backend='fake' "
            "in tests. The CatalogClient Protocol is the stable swap point."
        )

    # Protocol methods exist so type-checkers see a complete CatalogClient once
    # the constructor is unlocked; they are never reached while NotReady.
    def list_schema_fields(self, urn: str) -> list[str]:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def get_downstream(self, urn: str, column: str | None = None) -> list[str]:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def get_dataset_queries(self, urn: str) -> list[QueryRecord]:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def search_datasets(self, query: str, *, limit: int = 20) -> list[str]:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def save_forecast_document(self, urn: str, title: str, body_md: str) -> str:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def add_tags(self, urn: str, tag_urns: list[str]) -> None:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")

    def update_description(self, urn: str, description: str) -> None:  # pragma: no cover
        raise KitBackendNotReady("Kit backend not ready")
