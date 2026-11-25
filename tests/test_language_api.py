import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_languages(client: TestClient):
    response = client.get("/api/v1/languages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    codes = [lang["code"] for lang in data]
    assert "pl" in codes
    assert "en" in codes


def test_get_language_locale(client: TestClient):
    response = client.get("/api/v1/languages/pl")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "pl"
    assert "brand_title" in data["ui"]
    assert "taste_profile" in data["prompts"]

    response_en = client.get("/api/v1/languages/en")
    assert response_en.status_code == 200
    data_en = response_en.json()
    assert data_en["code"] == "en"
    assert data_en["ui"]["brand_title"] == "Curato"


def test_get_language_fallback(client: TestClient):
    response = client.get("/api/v1/languages/nonexistent_xyz")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "pl"
