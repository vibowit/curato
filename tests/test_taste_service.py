import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytest
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidStateException,
    NotFoundException,
    ValidationException,
)
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.sync import SyncState
from app.schemas.taste import TasteProfileUpdate, WeightedFeature
from app.services.taste import TasteService


class MockLLMProvider:
    def __init__(self, return_data: Optional[Dict[str, Any]] = None, fail: bool = False):
        self.return_data = return_data or {
            "summary": "Deep interest in gritty psychological crime and thoughtful sci-fi.",
            "genres": [
                {"name": "Crime", "weight": 0.95, "confidence": 0.9},
                {"name": "Sci-Fi", "weight": 0.85, "confidence": 0.85},
            ],
            "themes": [
                {"name": "Moral Ambiguity", "weight": 0.9, "confidence": 0.9},
            ],
            "directors_or_creators": ["Denis Villeneuve", "David Fincher"],
            "anti_preferences": ["Slapstick Humor"],
            "temporary_interests": [],
        }
        self.fail = fail
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_gemini"

    @property
    def model_name(self) -> str:
        return "mock-flash"

    async def generate_structured(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        self.call_count += 1
        if self.fail:
            return {"invalid_schema": True}
        return self.return_data


def seed_sample_history(db: Session):
    # Sync state
    sync = SyncState(
        provider="simkl",
        last_success_at=datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc),
        status="success",
    )
    db.add(sync)

    # Media items
    m1 = MediaItem(media_type="movie", title="Zodiac", year=2007, simkl_id="101")
    m2 = MediaItem(media_type="movie", title="Arrival", year=2016, simkl_id="102")
    m3 = MediaItem(media_type="movie", title="Bad Movie", year=2020, simkl_id="103")
    m4 = MediaItem(media_type="show", title="Severance", year=2022, simkl_id="104")
    m5 = MediaItem(media_type="movie", title="Unrated Movie", year=2018, simkl_id="105")
    m6 = MediaItem(media_type="show", title="Plan Show", year=2024, simkl_id="106")
    db.add_all([m1, m2, m3, m4, m5, m6])
    db.flush()

    # Watch history
    wh1 = WatchHistory(media_item_id=m1.id, status="completed", user_rating=9.5)
    wh2 = WatchHistory(media_item_id=m2.id, status="completed", user_rating=9.0)
    wh3 = WatchHistory(media_item_id=m3.id, status="completed", user_rating=3.0)
    wh4 = WatchHistory(media_item_id=m4.id, status="completed", user_rating=10.0)
    wh5 = WatchHistory(media_item_id=m5.id, status="completed", user_rating=None)
    wh6 = WatchHistory(media_item_id=m6.id, status="plantowatch", user_rating=None)
    db.add_all([wh1, wh2, wh3, wh4, wh5, wh6])
    db.commit()


def test_extract_history_empty_db(db_session: Session):
    service = TasteService(MockLLMProvider())
    with pytest.raises(InvalidStateException) as exc:
        service.extract_history_dataset(db_session)
    assert "Brak historii oglądania w lokalnej bazie" in str(exc.value)


def test_extract_history_dataset_success(db_session: Session):
    seed_sample_history(db_session)
    service = TasteService(MockLLMProvider())

    dataset = service.extract_history_dataset(db_session)
    assert dataset["based_on_sync_at"] is not None
    expected_sync = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)
    assert dataset["based_on_sync_at"].replace(tzinfo=timezone.utc) == expected_sync
    assert dataset["total_items"] == 6
    # Loved: rating >= 8.0 (Severance 10.0, Zodiac 9.5, Arrival 9.0)
    assert len(dataset["loved"]) == 3
    # Disliked: rating <= 5.0 (Bad Movie 3.0)
    assert len(dataset["disliked"]) == 1
    assert dataset["disliked"][0]["title"] == "Bad Movie"
    # Completed unrated
    assert len(dataset["completed_unrated"]) == 1
    assert dataset["completed_unrated"][0]["title"] == "Unrated Movie"
    # Plan to watch
    assert len(dataset["plantowatch"]) == 1
    assert dataset["plantowatch"][0]["title"] == "Plan Show"


@pytest.mark.asyncio
async def test_generate_profile_success(db_session: Session):
    seed_sample_history(db_session)
    mock_provider = MockLLMProvider()
    service = TasteService(mock_provider)

    profile = await service.generate_profile(db_session)
    assert profile.version == "v1.0-mock_gemini"
    assert profile.active is True
    assert profile.based_on_sync_at is not None
    expected_sync = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)
    assert profile.based_on_sync_at.replace(tzinfo=timezone.utc) == expected_sync
    assert mock_provider.call_count == 1

    content = json.loads(profile.profile_json)
    assert "psychological crime" in content["summary"]
    assert content["metadata"]["provider"] == "mock_gemini"
    assert content["metadata"]["analyzed_total_count"] == 6


@pytest.mark.asyncio
async def test_generate_profile_versioning_and_deactivation(db_session: Session):
    seed_sample_history(db_session)
    mock_provider = MockLLMProvider()
    service = TasteService(mock_provider)

    p1 = await service.generate_profile(db_session)
    assert p1.version == "v1.0-mock_gemini"
    assert p1.active is True

    p2 = await service.generate_profile(db_session)
    assert p2.version == "v2.0-mock_gemini"
    assert p2.active is True

    # Check that p1 was deactivated
    db_session.refresh(p1)
    assert p1.active is False


@pytest.mark.asyncio
async def test_generate_profile_validation_failure(db_session: Session):
    seed_sample_history(db_session)
    mock_provider = MockLLMProvider(fail=True)
    service = TasteService(mock_provider)

    with pytest.raises(ValidationException):
        await service.generate_profile(db_session)


@pytest.mark.asyncio
async def test_adjust_profile(db_session: Session):
    seed_sample_history(db_session)
    service = TasteService(MockLLMProvider())
    await service.generate_profile(db_session)

    # Adjust profile by restricting animation and updating anti-preferences
    update = TasteProfileUpdate(
        anti_preferences=["Slapstick Humor", "Excessive Animation"],
        genres=[
            WeightedFeature(name="Crime", weight=0.95, confidence=0.9),
            WeightedFeature(name="Sci-Fi", weight=0.7, confidence=0.85, note="Scaled down"),
        ],
        change_note="User requested limiting animation and rebalancing sci-fi",
    )

    adjusted = service.adjust_profile(db_session, update)
    assert adjusted.version == "v1.1-manual"
    assert adjusted.active is True

    content = json.loads(adjusted.profile_json)
    assert "Excessive Animation" in content["anti_preferences"]
    assert content["metadata"]["manual_adjustments_count"] == 1
    notes = content["metadata"]["change_notes"]
    assert "limiting animation" in notes[0]["note"]

    # Previous active profile should now be inactive
    p1 = service.get_profile_by_version(db_session, "v1.0-mock_gemini")
    assert p1.active is False


@pytest.mark.asyncio
async def test_activate_version(db_session: Session):
    seed_sample_history(db_session)
    service = TasteService(MockLLMProvider())

    p1 = await service.generate_profile(db_session)
    p2 = await service.generate_profile(db_session)
    assert p2.active is True
    assert p1.active is False

    # Roll back / reactivate p1
    service.activate_version(db_session, p1.version)
    db_session.refresh(p1)
    db_session.refresh(p2)
    assert p1.active is True
    assert p2.active is False


def test_get_profile_by_version_not_found(db_session: Session):
    service = TasteService(MockLLMProvider())
    with pytest.raises(NotFoundException):
        service.get_profile_by_version(db_session, "v999.0")


@pytest.mark.asyncio
async def test_generate_profile_with_language(db_session: Session):
    seed_sample_history(db_session)
    mock_provider = MockLLMProvider()
    service = TasteService(mock_provider)

    from app.schemas.taste import TasteProfileGenerateRequest

    req_en = TasteProfileGenerateRequest(language="en")
    profile_en = await service.generate_profile(db_session, req_en)
    content_en = json.loads(profile_en.profile_json)
    assert content_en["metadata"]["language"] == "en"

    req_pl = TasteProfileGenerateRequest(language="pl")
    profile_pl = await service.generate_profile(db_session, req_pl)
    content_pl = json.loads(profile_pl.profile_json)
    assert content_pl["metadata"]["language"] == "pl"
