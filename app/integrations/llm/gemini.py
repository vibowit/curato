import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.errors import (
    AuthRequiredException,
    RateLimitedException,
    UpstreamErrorException,
)

logger = logging.getLogger("movie_recommend.integrations.llm.gemini")


class GeminiLLMClient:
    """Asynchronous client for Google Gemini API returning structured JSON."""

    BASE_URL: str = "https://generativelanguage.googleapis.com"
    DEFAULT_MODELS: List[str] = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
    ]

    _cached_working_model: Optional[str] = None

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        raw_key = api_key or (
            settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
        )
        self._api_key = raw_key
        # Check explicit model, then cached working model, then config, then default
        configured_model = model or self._cached_working_model or settings.GEMINI_MODEL
        # Normalize deprecated or non-lite models (which have harsh rate limits) to lite
        if configured_model and (
            any(v in configured_model for v in ("1.5", "2.0", "2.5"))
            or configured_model in ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash")
        ):
            configured_model = "gemini-3.1-flash-lite"

        self._model = configured_model or self.DEFAULT_MODELS[0]
        self.timeout = timeout
        self._external_client = client

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=self.timeout)

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """Strips markdown code blocks if the LLM output wrapped the JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    async def discover_models(self, client: httpx.AsyncClient) -> List[Tuple[str, str]]:
        """Queries Google's ListModels endpoint to get all supported models for this API key."""
        if not self._api_key:
            return []

        discovered: List[Tuple[str, str]] = []
        for api_version in ("v1beta", "v1"):
            url = f"{self.BASE_URL}/{api_version}/models"
            try:
                res = await client.get(url, params={"key": self._api_key})
                if res.status_code == 200:
                    data = res.json()
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        name = m.get("name", "").replace("models/", "")
                        bad_keywords = ("image", "tts", "audio", "embed")
                        if (
                            "generateContent" in methods
                            and not any(bad in name.lower() for bad in bad_keywords)
                            and not any(dead in name for dead in ("1.5", "2.0", "2.5"))
                        ):
                            discovered.append((name, api_version))
                    if discovered:
                        break
            except Exception as e:
                logger.debug("Failed discovering models on %s: %s", api_version, e)
                continue

        return sorted(
            discovered,
            key=lambda item: (
                0 if "flash-lite" in item[0].lower() else 1,
                0 if "flash" in item[0].lower() else 2,
                item[0],
            ),
        )

    async def generate_structured(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calls Gemini generateContent endpoint and parses response as JSON dict."""
        if not self._api_key:
            raise AuthRequiredException(
                message="GEMINI_API_KEY is not configured.",
                details={"provider": "gemini"},
            )

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        # Try designated model, and fall back to alternatives if model not found or rate limited
        models_to_try: List[Tuple[str, str]] = [(self._model, "v1beta")] + [
            (m, "v1beta") for m in self.DEFAULT_MODELS if m != self._model
        ]
        last_error: Optional[str] = None
        tried_models = set()

        client = self._get_client()
        try:
            for model_candidate, api_ver in models_to_try:
                tried_models.add(model_candidate)
                url = f"{self.BASE_URL}/{api_ver}/models/{model_candidate}:generateContent"
                params = {"key": self._api_key}

                for attempt in range(3):
                    try:
                        response = await client.post(
                            url,
                            params=params,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                        )
                    except httpx.TimeoutException as exc:
                        logger.warning(
                            "Timeout calling Gemini API (%s): %s, trying fallback...",
                            model_candidate,
                            exc,
                        )
                        last_error = f"Model {model_candidate} timed out"
                        break
                    except httpx.RequestError as exc:
                        logger.warning(
                            "Network error calling Gemini API (%s): %s, trying fallback...",
                            model_candidate,
                            exc,
                        )
                        last_error = f"Model {model_candidate} network error: {exc}"
                        break

                    if response.status_code == 200:
                        self._model = model_candidate
                        GeminiLLMClient._cached_working_model = model_candidate
                        return self._parse_response(response.json())

                    if response.status_code in (401, 403):
                        logger.error(
                            "Authentication failed for Gemini API (HTTP %d)",
                            response.status_code,
                        )
                        raise AuthRequiredException(
                            message="Invalid or unauthorized Gemini API key.",
                            details={"provider": "gemini", "status_code": response.status_code},
                        )

                    # For transient 503, retry up to 2 times after backoff
                    if response.status_code == 503 and attempt < 2:
                        backoff = 0.5 * (attempt + 1)
                        logger.debug("503 on %s, retrying in %.1fs...", model_candidate, backoff)
                        await asyncio.sleep(backoff)
                        continue

                    if response.status_code in (404, 429, 500, 502, 503, 504):
                        logger.warning(
                            "Model %s returned HTTP %d on Gemini API, trying fallback...",
                            model_candidate,
                            response.status_code,
                        )
                        last_error = f"Model {model_candidate} returned HTTP {response.status_code}"
                        break

                    # Any other HTTP error
                    logger.error(
                        "Gemini API returned HTTP %d: %s",
                        response.status_code,
                        response.text[:200],
                    )
                    raise UpstreamErrorException(
                        message=f"Gemini API returned error: HTTP {response.status_code}",
                        details={"provider": "gemini", "status_code": response.status_code},
                    )

            if last_error and "429" in last_error:
                raise RateLimitedException(
                    message=f"Gemini API rate limit exceeded across fallback models: {last_error}",
                    details={"provider": "gemini"},
                )
            raise UpstreamErrorException(
                message=f"No compatible Gemini model found. Last error: {last_error}",
                details={"provider": "gemini"},
            )
        finally:
            if self._external_client is None:
                await client.aclose()

    def _parse_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parses and validates candidates text as a JSON dictionary."""
        candidates = data.get("candidates", [])
        if not candidates:
            raise UpstreamErrorException(
                message="Gemini API returned no candidates in response",
                details={"provider": "gemini", "raw_response": data},
            )

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts or "text" not in parts[0]:
            raise UpstreamErrorException(
                message="Gemini candidate content has no text parts",
                details={"provider": "gemini"},
            )

        raw_text = parts[0]["text"]
        clean_text = self._clean_json_text(raw_text)

        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                parsed = {"evaluations": parsed}
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not an object/dictionary or list")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "Failed to parse Gemini output as JSON: %s (raw text: %s)",
                exc,
                raw_text[:200],
            )
            raise UpstreamErrorException(
                message="LLM returned response that could not be parsed as JSON object",
                details={"provider": "gemini", "error": str(exc)},
            ) from exc
