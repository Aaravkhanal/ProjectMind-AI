"""Tests for provider management endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app
    return TestClient(app)


def test_providers_list_returns_200(client):
    r = client.get("/providers")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)


def test_providers_catalog_returns_list(client):
    r = client.get("/providers/catalog")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)
    assert len(data["providers"]) > 0


def test_providers_catalog_has_required_fields(client):
    r = client.get("/providers/catalog")
    first = r.json()["providers"][0]
    assert "id" in first or "name" in first
    assert "label" in first


def test_providers_catalog_includes_openai(client):
    r = client.get("/providers/catalog")
    ids = [p.get("id", p.get("name", "")) for p in r.json()["providers"]]
    assert any("openai" in i.lower() for i in ids)


def test_providers_recommendations_returns_200(client):
    r = client.get("/providers/recommendations")
    assert r.status_code == 200
