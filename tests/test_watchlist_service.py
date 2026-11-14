import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidStateException
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun
from app.services.watchlist import WatchlistService


class DummySimklWriteClient:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.write_calls_count = 0
        self.written_payloads = []

    async def add_to_list(self, media_type: str, items: list):
        self.write_calls_count += 1
        self.written_payloads.append({"media_type": media_type, "items": items})
        if self.should_fail:
            raise RuntimeError("Simkl API write failed")
        return {
            "added": {media_type: len(items)},
            "not_found": {media_type: []},
        }


def _create_sample_run_and_rec(db: Session, status: str = "pending") -> Recommendation:
    media = MediaItem(
        media_type="movie",
        title="Arrival",
        year=2016,
        simkl_id=532001,
        tmdb_id=329865,
        imdb_id="tt2543164",
    )
    db.add(media)
    db.flush()

    run = RecommendationRun(
        status="completed",
        profile_version="v1.0",
        model_provider="gemini",
        model_name="gemini-2.5-flash",
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        run_id=run.id,
        media_item_id=media.id,
        match_score=92.0,
        confidence=0.88,
        reason="Intelligent sci-fi with emotional core.",
        status=status,
    )
    db.add(rec)
    db.commit()
    return rec


@pytest.mark.asyncio
async def test_watchlist_blocks_unapproved_recommendation(db_session: Session):
    rec = _create_sample_run_and_rec(db_session, status="pending")
    client = DummySimklWriteClient()
    service = WatchlistService(db_session=db_session, simkl_client=client)

    # Invariant: Must fail when status is 'pending'
    with pytest.raises(InvalidStateException) as exc_info:
        await service.add_approved_recommendation(recommendation_id=rec.id)

    assert "approval is required" in str(exc_info.value.message).lower()
    assert client.write_calls_count == 0  # CRITICAL INVARIANT: Zero writes


@pytest.mark.asyncio
async def test_watchlist_blocks_rejected_recommendation(db_session: Session):
    rec = _create_sample_run_and_rec(db_session, status="rejected")
    client = DummySimklWriteClient()
    service = WatchlistService(db_session=db_session, simkl_client=client)

    with pytest.raises(InvalidStateException):
        await service.add_approved_recommendation(recommendation_id=rec.id)

    assert client.write_calls_count == 0


@pytest.mark.asyncio
async def test_watchlist_adds_accepted_recommendation(db_session: Session):
    rec = _create_sample_run_and_rec(db_session, status="accepted")
    client = DummySimklWriteClient()
    service = WatchlistService(db_session=db_session, simkl_client=client)

    result = await service.add_approved_recommendation(recommendation_id=rec.id)

    assert result.success is True
    assert result.status == "added"
    assert client.write_calls_count == 1

    # Verify payload format
    payload = client.written_payloads[0]
    assert payload["media_type"] == "movies"
    assert payload["items"][0]["title"] == "Arrival"
    assert payload["items"][0]["to"] == "plantowatch"
    assert payload["items"][0]["ids"]["simkl"] == 532001

    # Verify recommendation status updated in DB
    updated_rec = db_session.get(Recommendation, rec.id)
    assert updated_rec.status == "added"

    # Verify WatchHistory created with plantowatch
    history = db_session.scalar(
        select(WatchHistory).where(WatchHistory.media_item_id == rec.media_item_id)
    )
    assert history is not None
    assert history.status == "plantowatch"


@pytest.mark.asyncio
async def test_watchlist_idempotency_on_repeated_add(db_session: Session):
    rec = _create_sample_run_and_rec(db_session, status="accepted")
    client = DummySimklWriteClient()
    service = WatchlistService(db_session=db_session, simkl_client=client)

    # First add: succeeds and performs write
    res1 = await service.add_approved_recommendation(recommendation_id=rec.id)
    assert res1.success is True
    assert res1.status == "added"
    assert client.write_calls_count == 1

    # Second add: already added! Should be idempotent and NOT call Simkl write again
    res2 = await service.add_approved_recommendation(recommendation_id=rec.id)
    assert res2.success is True
    assert res2.status == "already_added"
    assert client.write_calls_count == 1  # Still 1, no duplicate external call
