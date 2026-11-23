import json
from datetime import datetime, timezone

import httpx
import pytest

from app.integrations.simkl import (
    SimklAuthError,
    SimklClient,
    SimklRateLimitError,
    SimklUpstreamError,
)


@pytest.mark.asyncio
async def test_simkl_client_headers_and_auth():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["simkl-api-key"] == "test_client_id"
        assert request.headers["Authorization"] == "Bearer test_user_token"
        assert request.headers["User-Agent"].startswith("PersonalMovieRecommender")
        return httpx.Response(200, json={"user": {"name": "test_user"}})

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="test_user_token",
        transport=transport,
    )

    settings = await client.get_user_settings()
    assert settings["user"]["name"] == "test_user"
    assert client.write_calls_count == 0


@pytest.mark.asyncio
async def test_simkl_client_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="bad_token",
        transport=transport,
    )

    with pytest.raises(SimklAuthError) as exc_info:
        await client.get_user_settings()
    assert exc_info.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_simkl_client_rate_limit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limit_exceeded"})

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="test_user_token",
        transport=transport,
        max_retries=1,
    )

    with pytest.raises(SimklRateLimitError) as exc_info:
        await client.get_activities()
    assert exc_info.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_simkl_client_upstream_error_on_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="test_user_token",
        transport=transport,
        max_retries=1,
    )

    with pytest.raises(SimklUpstreamError) as exc_info:
        await client.get_activities()
    assert exc_info.value.code == "UPSTREAM_ERROR"


@pytest.mark.asyncio
async def test_simkl_client_get_items():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "sync/all-items/movies" in str(request.url)
        assert "date_from=2026-01-01T00%3A00%3A00Z" in str(request.url)
        data = {
            "movies": [
                {
                    "title": "Inception",
                    "year": 2010,
                    "ids": {"simkl": 12345, "tmdb": 27205, "imdb": "tt1375666"},
                    "status": "completed",
                    "user_rating": 9,
                }
            ]
        }
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="test_user_token",
        transport=transport,
    )

    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    items = await client.get_items("movies", date_from=dt)
    assert len(items) == 1
    assert items[0]["title"] == "Inception"
    assert items[0]["user_rating"] == 9
    assert client.write_calls_count == 0


@pytest.mark.asyncio
async def test_simkl_client_add_to_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "sync/add-to-list" in str(request.url)
        payload = json.loads(request.content.decode("utf-8"))
        assert "movies" in payload
        assert len(payload["movies"]) == 1
        assert payload["movies"][0]["title"] == "Dune: Part Two"
        assert payload["movies"][0]["to"] == "plantowatch"
        assert payload["movies"][0]["ids"]["simkl"] == 99999
        resp_data = {"added": {"movies": 1, "shows": 0}, "not_found": {"movies": []}}
        return httpx.Response(200, json=resp_data)

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="test_user_token",
        transport=transport,
    )

    result = await client.add_to_list(
        media_type="movies",
        items=[
            {
                "title": "Dune: Part Two",
                "year": 2024,
                "ids": {"simkl": 99999, "tmdb": 693134},
                "to": "plantowatch",
            }
        ],
    )
    assert result["added"]["movies"] == 1
    assert client.write_calls_count == 1


@pytest.mark.asyncio
async def test_simkl_client_auto_refresh_on_401():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        calls.append(url_str)

        # 1. First call to /users/settings -> 401 token expired
        if "users/settings" in url_str and len(calls) == 1:
            assert request.headers["Authorization"] == "Bearer old_token"
            return httpx.Response(
                401,
                json={"error": "invalid_token", "message": "Access token has expired"},
            )

        # 2. Token refresh request
        if "oauth2/token" in url_str:
            assert request.method == "POST"
            assert request.headers["simkl-api-key"] == "test_client_id"
            content = request.content.decode("utf-8")
            assert "grant_type=refresh_token" in content
            assert "refresh_token=old_refresh" in content
            return httpx.Response(
                200,
                json={
                    "access_token": "new_refreshed_token",
                    "refresh_token": "new_rotated_refresh",
                    "expires_in": 604800,
                    "token_type": "Bearer",
                },
            )

        # 3. Retried call to /users/settings with new token
        if "users/settings" in url_str and len(calls) == 3:
            assert request.headers["Authorization"] == "Bearer new_refreshed_token"
            return httpx.Response(200, json={"user": {"name": "auto_refreshed_user"}})

        return httpx.Response(500, text="Unexpected request")

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="old_token",
        refresh_token="old_refresh",
        transport=transport,
    )

    settings_resp = await client.get_user_settings()
    assert settings_resp["user"]["name"] == "auto_refreshed_user"
    assert client.user_token == "new_refreshed_token"
    assert client.refresh_token == "new_rotated_refresh"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_simkl_client_refresh_failure_raises_auth_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        calls.append(url_str)

        if "users/settings" in url_str:
            return httpx.Response(401, json={"error": "invalid_token"})

        if "oauth2/token" in url_str:
            return httpx.Response(400, json={"error": "invalid_grant", "message": "Token expired"})

        return httpx.Response(500, text="Unexpected")

    transport = httpx.MockTransport(handler)
    client = SimklClient(
        client_id="test_client_id",
        user_token="old_token",
        refresh_token="expired_refresh",
        transport=transport,
    )

    with pytest.raises(SimklAuthError) as exc_info:
        await client.get_user_settings()
    assert exc_info.value.code == "AUTH_REQUIRED"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_simkl_client_loads_tokens_from_app_settings(db_session, monkeypatch):
    from app.core.tokens import save_stored_simkl_tokens

    # Route SessionLocal and .env updates to in-memory test database
    monkeypatch.setattr("app.core.tokens.SessionLocal", lambda: db_session)
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
    monkeypatch.setattr("app.core.tokens.try_update_env_tokens", lambda *args, **kwargs: None)

    # Persist mock tokens in app_settings table via in-memory session
    save_stored_simkl_tokens(
        access_token="db_access_token",
        refresh_token="db_refresh_token",
        expires_in=3600,
        db=db_session,
    )

    # Initialize client without passing explicit tokens
    client = SimklClient(client_id="test_client_id")
    assert client.user_token == "db_access_token"
    assert client.refresh_token == "db_refresh_token"

