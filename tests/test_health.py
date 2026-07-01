"""Tests for the health and root endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app
    return TestClient(app)


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "ProjectMind AI"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "python" in data


def test_root_returns_service_name(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "ProjectMind AI"
    assert "version" in data


def test_health_uptime_is_non_negative(client):
    r = client.get("/health")
    assert r.json()["uptime_seconds"] >= 0


def test_health_timestamp_present(client):
    r = client.get("/health")
    ts = r.json()["timestamp"]
    assert "T" in ts  # ISO 8601 format
