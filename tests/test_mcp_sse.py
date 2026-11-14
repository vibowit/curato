from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import create_app


def test_mcp_sse_unauthenticated_when_no_key_configured(monkeypatch):
    """When MCP_API_KEY is None, the SSE endpoint is accessible without credentials."""
    monkeypatch.setattr(settings, "MCP_API_KEY", None)
    app = create_app()
    with TestClient(app) as client:
        # Requesting /mcp/sse without auth should not return 401
        with client.stream("GET", "/mcp/sse") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")


def test_mcp_sse_auth_protection(monkeypatch):
    """When MCP_API_KEY is set, requests without valid token must return 401."""
    test_key = "super-secret-mcp-key-12345"
    monkeypatch.setattr(settings, "MCP_API_KEY", SecretStr(test_key))
    app = create_app()

    with TestClient(app) as client:
        # 1. Missing header
        res_no_auth = client.get("/mcp/sse")
        assert res_no_auth.status_code == 401
        assert res_no_auth.json()["error"] == "Unauthorized"

        # 2. Invalid Bearer header
        res_bad_auth = client.get("/mcp/sse", headers={"Authorization": "Bearer wrong-key"})
        assert res_bad_auth.status_code == 401

        # 3. Valid Bearer header
        with client.stream(
            "GET", "/mcp/sse", headers={"Authorization": f"Bearer {test_key}"}
        ) as res_valid_bearer:
            assert res_valid_bearer.status_code == 200
            assert "text/event-stream" in res_valid_bearer.headers.get("content-type", "")

        # 4. Valid query param (?api_key=...)
        with client.stream("GET", f"/mcp/sse?api_key={test_key}") as res_valid_query:
            assert res_valid_query.status_code == 200
            assert "text/event-stream" in res_valid_query.headers.get("content-type", "")
