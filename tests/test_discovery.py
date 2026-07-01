"""Tests for the environment discovery endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app
    return TestClient(app)


def test_discover_scan_returns_profile_shape(client):
    r = client.get("/discover/scan?project_path=.")
    assert r.status_code == 200
    data = r.json()
    assert "profile" in data
    profile = data["profile"]
    assert "os_name" in profile
    assert "editor" in profile
    assert "scan_duration_ms" in profile
    assert "capabilities" in profile


def test_discover_profile_returns_shape(client):
    r = client.get("/discover/profile?project_path=.")
    assert r.status_code == 200
    data = r.json()
    assert "editor" in data
    assert "os_name" in data


def test_discover_capabilities_returns_dict(client):
    r = client.get("/discover/capabilities?project_path=.")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    # capabilities may be top-level or nested
    caps = data.get("capabilities", data)
    assert "default_model" in caps or "best_coding" in caps


def test_discover_models_returns_shape(client):
    r = client.get("/discover/models?project_path=.")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "models" in data
    assert isinstance(data["models"], list)


def test_discover_providers_returns_shape(client):
    r = client.get("/discover/providers?project_path=.")
    assert r.status_code == 200
    data = r.json()
    # Either a list or a dict with a providers key
    assert isinstance(data, (list, dict))


def test_discover_mcp_returns_list(client):
    r = client.get("/discover/mcp?project_path=.")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))
