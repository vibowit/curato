import json

import httpx
import pytest

from app.core.errors import (
    AuthRequiredException,
    RateLimitedException,
    UpstreamErrorException,
)
from app.integrations.llm.gemini import GeminiLLMClient


@pytest.mark.asyncio
async def test_gemini_client_missing_key():
    client = GeminiLLMClient(api_key=None)
    client._api_key = None  # Ensure no key
    with pytest.raises(AuthRequiredException) as exc:
        await client.generate_structured("Analyze taste")
    assert "GEMINI_API_KEY is not configured" in str(exc.value)


@pytest.mark.asyncio
async def test_gemini_client_success():
    expected_result = {
        "summary": "Loves hard sci-fi and crime procedurals",
        "genres": [{"name": "Sci-Fi", "weight": 0.9, "confidence": 0.85}],
    }

    def mock_handler(request: httpx.Request):
        assert "models/gemini-2.5-flash:generateContent" in str(request.url)
        assert request.url.params.get("key") == "fake_gemini_key"
        body = json.loads(request.content.decode("utf-8"))
        assert "contents" in body

        response_payload = {
            "candidates": [
                {"content": {"parts": [{"text": f"```json\n{json.dumps(expected_result)}\n```"}]}}
            ]
        }
        return httpx.Response(200, json=response_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    gemini = GeminiLLMClient(api_key="fake_gemini_key", client=mock_client)

    result = await gemini.generate_structured("Prompt text", system_instruction="System rule")
    assert result == expected_result
    assert gemini.provider_name == "gemini"
    assert gemini.model_name == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_gemini_client_rate_limited():
    def mock_handler(request: httpx.Request):
        return httpx.Response(429, json={"error": {"message": "Resource exhausted"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    gemini = GeminiLLMClient(api_key="fake_gemini_key", client=mock_client)

    with pytest.raises(RateLimitedException):
        await gemini.generate_structured("Prompt")


@pytest.mark.asyncio
async def test_gemini_client_auth_error():
    def mock_handler(request: httpx.Request):
        return httpx.Response(401, json={"error": {"message": "API_KEY_INVALID"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    gemini = GeminiLLMClient(api_key="fake_gemini_key", client=mock_client)

    with pytest.raises(AuthRequiredException):
        await gemini.generate_structured("Prompt")


@pytest.mark.asyncio
async def test_gemini_client_fallback_on_404():
    calls = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        calls.append(url_str)
        if "gemini-2.5-flash" in url_str:
            return httpx.Response(404, json={"error": {"message": "Model not found"}})
        if "gemini-2.0-flash" in url_str:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": json.dumps({"summary": "Fallback model works"})}]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(500)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    gemini = GeminiLLMClient(api_key="fake_gemini_key", client=mock_client)

    res = await gemini.generate_structured("Prompt")
    assert res == {"summary": "Fallback model works"}
    assert gemini.model_name == "gemini-2.0-flash"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_gemini_client_invalid_json():
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Not a valid json at all!"}]}}]},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    gemini = GeminiLLMClient(api_key="fake_gemini_key", client=mock_client)

    with pytest.raises(UpstreamErrorException) as exc:
        await gemini.generate_structured("Prompt")
    assert "could not be parsed as JSON object" in str(exc.value)
