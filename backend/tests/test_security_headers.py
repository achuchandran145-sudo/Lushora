from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_api_responses_include_security_headers_and_are_not_cacheable():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-permitted-cross-domain-policies"] == "none"
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'; base-uri 'none'"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


def test_hsts_is_enabled_only_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    production_response = client.get("/api/health")
    assert production_response.status_code == 200
    assert production_response.headers["strict-transport-security"] == "max-age=31536000"

    monkeypatch.setenv("APP_ENV", "development")
    development_response = client.get("/api/health")
    assert development_response.status_code == 200
    assert "strict-transport-security" not in development_response.headers
