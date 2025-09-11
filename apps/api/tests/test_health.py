"""Tests para endpoints de health check."""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test del endpoint de health check básico."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_app_runs():
    """Test básico que la aplicación se ejecuta."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
