"""Tests for Repository Brain endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app
    return TestClient(app)


def test_brain_summary_default_path(client):
    r = client.get("/brain/summary")
    # project_path defaults to "." — should return 200 with summary data
    assert r.status_code == 200


def test_brain_summary_nonexistent_project(client):
    r = client.get("/brain/summary?project_path=/tmp/nonexistent-xyz")
    # Should return 200 with empty/default data, not 500
    assert r.status_code in (200, 404)


def test_brain_hotspots_returns_list(client):
    r = client.get("/brain/hotspots?project_path=/tmp/nonexistent-xyz")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert isinstance(r.json(), list)


def test_brain_debt_returns_list(client):
    r = client.get("/brain/debt?project_path=/tmp/nonexistent-xyz")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert isinstance(r.json(), list)
