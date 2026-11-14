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
