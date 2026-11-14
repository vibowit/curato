import pytest
from pydantic import ValidationError

from app.schemas.taste import (
    TasteProfileContent,
    TasteProfileGenerateRequest,
    TasteProfileUpdate,
    WeightedFeature,
)


def test_weighted_feature_valid():
    feature = WeightedFeature(name="Sci-Fi", weight=0.9, confidence=0.85, note="Loves hard sci-fi")
    assert feature.name == "Sci-Fi"
    assert feature.weight == 0.9
    assert feature.confidence == 0.85
    assert feature.note == "Loves hard sci-fi"


def test_weighted_feature_invalid_bounds():
    with pytest.raises(ValidationError):
        WeightedFeature(name="Invalid", weight=1.5, confidence=0.5)

    with pytest.raises(ValidationError):
        WeightedFeature(name="Invalid", weight=-0.1, confidence=0.5)

    with pytest.raises(ValidationError):
        WeightedFeature(name="Invalid", weight=0.5, confidence=1.1)


def test_taste_profile_content_defaults():
    content = TasteProfileContent(summary="User enjoys psychological thrillers.")
    assert content.summary == "User enjoys psychological thrillers."
    assert content.genres == []
    assert content.themes == []
    assert content.directors_or_creators == []
    assert content.anti_preferences == []
    assert content.temporary_interests == []
    assert content.metadata == {}


def test_taste_profile_content_full():
    content = TasteProfileContent(
        summary="User enjoys psychological thrillers.",
        genres=[WeightedFeature(name="Thriller", weight=0.95, confidence=0.9)],
        themes=[WeightedFeature(name="Moral Ambiguity", weight=0.9, confidence=0.85)],
        directors_or_creators=["David Fincher", "Denis Villeneuve"],
        anti_preferences=["Slapstick Comedy"],
        temporary_interests=[WeightedFeature(name="Cyberpunk", weight=0.8, confidence=0.7)],
        metadata={"model": "gemini-2.5-flash"},
    )
    assert len(content.genres) == 1
    assert content.genres[0].name == "Thriller"
    assert "David Fincher" in content.directors_or_creators
    assert content.metadata["model"] == "gemini-2.5-flash"


def test_generate_request_validation():
    req = TasteProfileGenerateRequest()
    assert req.min_rating_loved == 8.0
    assert req.max_rating_disliked == 5.0
    assert req.include_plantowatch is True

    with pytest.raises(ValidationError):
        TasteProfileGenerateRequest(min_rating_loved=12.0)


def test_update_request_optional_fields():
    update = TasteProfileUpdate(
        anti_preferences=["Excessive Gore", "Slapstick"],
        change_note="User requested restricting gore",
    )
    assert update.summary is None
    assert update.anti_preferences == ["Excessive Gore", "Slapstick"]
    assert update.change_note == "User requested restricting gore"
