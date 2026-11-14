from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.errors import AuthRequiredException, NotFoundException
from app.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data

    # Ensure response headers include X-Request-ID
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0


def test_health_preserves_custom_request_id():
    app = create_app()
    client = TestClient(app)

    custom_id = "test-custom-req-id-12345"
    response = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


def test_app_exception_handling():
    app = create_app()
    test_router = APIRouter()

    @test_router.get("/api/test-auth-error")
    def trigger_auth():
        raise AuthRequiredException("Please log in with Simkl OAuth")

    @test_router.get("/api/test-not-found")
    def trigger_nf():
        raise NotFoundException("Media item 999 not found")

    app.include_router(test_router)
    client = TestClient(app)

    # Test 401 AUTH_REQUIRED
    res1 = client.get("/api/test-auth-error")
    assert res1.status_code == 401
    d1 = res1.json()
    assert d1["error_code"] == "AUTH_REQUIRED"
    assert d1["message"] == "Please log in with Simkl OAuth"
    assert "request_id" in d1

    # Test 404 NOT_FOUND
    res2 = client.get("/api/test-not-found")
    assert res2.status_code == 404
    d2 = res2.json()
    assert d2["error_code"] == "NOT_FOUND"
    assert d2["message"] == "Media item 999 not found"
