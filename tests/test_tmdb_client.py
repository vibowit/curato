import httpx
import pytest

from app.integrations.tmdb import (
    TMDBAuthError,
    TMDBClient,
    TMDBRateLimitError,
    TMDBUpstreamError,
)


@pytest.mark.asyncio
async def test_tmdb_client_auth_with_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api_key=my_test_key" in str(request.url)
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"results": [{"id": 550, "title": "Fight Club"}]})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="my_test_key", transport=transport)

    res = await client.discover_movies()
    assert len(res["results"]) == 1
    assert res["results"][0]["title"] == "Fight Club"


@pytest.mark.asyncio
async def test_tmdb_client_auth_with_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer my_bearer_token"
        assert "api_key" not in str(request.url)
        return httpx.Response(200, json={"results": [{"id": 1399, "name": "Game of Thrones"}]})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(read_access_token="my_bearer_token", transport=transport)

    res = await client.discover_shows()
    assert len(res["results"]) == 1
    assert res["results"][0]["name"] == "Game of Thrones"


@pytest.mark.asyncio
async def test_tmdb_client_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "Invalid API key."})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="invalid_key", transport=transport)

    with pytest.raises(TMDBAuthError) as exc_info:
        await client.discover_movies()
    assert exc_info.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_tmdb_client_rate_limit_error():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            429, headers={"Retry-After": "0.01"}, json={"status_message": "Rate limit"}
        )

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="my_key", transport=transport, max_retries=2)

    with pytest.raises(TMDBRateLimitError) as exc_info:
        await client.discover_movies()
    assert exc_info.value.code == "RATE_LIMITED"
    assert call_count == 2


@pytest.mark.asyncio
async def test_tmdb_client_upstream_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status_message": "Internal error"})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="my_key", transport=transport, max_retries=2)

    with pytest.raises(TMDBUpstreamError) as exc_info:
        await client.discover_movies()
    assert exc_info.value.code == "UPSTREAM_ERROR"


@pytest.mark.asyncio
async def test_tmdb_client_methods_and_parameters():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/search/person" in path:
            return httpx.Response(200, json={"results": [{"id": 138, "name": "Quentin Tarantino"}]})
        elif "/movie/550/recommendations" in path:
            return httpx.Response(200, json={"results": [{"id": 680, "title": "Pulp Fiction"}]})
        elif "/movie/550" in path:
            return httpx.Response(
                200,
                json={
                    "id": 550,
                    "title": "Fight Club",
                    "external_ids": {"imdb_id": "tt0137523"},
                },
            )
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = TMDBClient(api_key="my_key", transport=transport)

    person = await client.search_person("Quentin Tarantino")
    assert person["results"][0]["name"] == "Quentin Tarantino"

    recs = await client.get_movie_recommendations(550)
    assert recs["results"][0]["title"] == "Pulp Fiction"

    details = await client.get_movie_details(550)
    assert details["external_ids"]["imdb_id"] == "tt0137523"
