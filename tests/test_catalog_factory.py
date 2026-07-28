"""Catalog access-layer factory — Kit default; GraphQL explicit fallback."""

from __future__ import annotations

import pytest

from premortem.catalog import (
    FakeCatalogClient,
    GraphqlCatalogClient,
    KitCatalogClient,
    create_catalog_client,
)


def test_factory_defaults_to_kit(monkeypatch):
    pytest.importorskip("datahub")
    pytest.importorskip("datahub_agent_context")
    monkeypatch.delenv("PREMORTEM_CATALOG", raising=False)
    monkeypatch.delenv("PREMORTEM_CATALOG_BACKEND", raising=False)
    client = create_catalog_client(gms_url="http://localhost:8080", write_back_enabled=False)
    assert isinstance(client, KitCatalogClient)


def test_factory_explicit_graphql():
    client = create_catalog_client(
        backend="graphql", gms_url="http://localhost:8080", write_back_enabled=False
    )
    assert isinstance(client, GraphqlCatalogClient)


def test_factory_fake_backend():
    client = create_catalog_client(backend="fake", write_back_enabled=True)
    assert isinstance(client, FakeCatalogClient)


def test_factory_unknown_backend():
    with pytest.raises(ValueError, match="Unknown catalog backend"):
        create_catalog_client(backend="soap")


def test_factory_env_catalog(monkeypatch):
    monkeypatch.setenv("PREMORTEM_CATALOG", "fake")
    client = create_catalog_client()
    assert isinstance(client, FakeCatalogClient)


def test_factory_env_backend_legacy(monkeypatch):
    monkeypatch.delenv("PREMORTEM_CATALOG", raising=False)
    monkeypatch.setenv("PREMORTEM_CATALOG_BACKEND", "fake")
    client = create_catalog_client()
    assert isinstance(client, FakeCatalogClient)
