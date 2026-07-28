"""Catalog access-layer factory — GraphQL default; Kit reserved for post-spike."""

from __future__ import annotations

import pytest

from premortem.catalog import (
    FakeCatalogClient,
    GraphqlCatalogClient,
    KitBackendNotReady,
    create_catalog_client,
)


def test_factory_defaults_to_graphql():
    client = create_catalog_client(gms_url="http://localhost:8080", write_back_enabled=False)
    assert isinstance(client, GraphqlCatalogClient)


def test_factory_explicit_graphql():
    client = create_catalog_client(
        backend="graphql", gms_url="http://localhost:8080", write_back_enabled=False
    )
    assert isinstance(client, GraphqlCatalogClient)


def test_factory_fake_backend():
    client = create_catalog_client(backend="fake", write_back_enabled=True)
    assert isinstance(client, FakeCatalogClient)


def test_factory_kit_fails_fast():
    with pytest.raises(KitBackendNotReady, match="S1"):
        create_catalog_client(backend="kit")


def test_factory_unknown_backend():
    with pytest.raises(ValueError, match="Unknown catalog backend"):
        create_catalog_client(backend="soap")


def test_factory_env_backend(monkeypatch):
    monkeypatch.setenv("PREMORTEM_CATALOG_BACKEND", "fake")
    client = create_catalog_client()
    assert isinstance(client, FakeCatalogClient)
