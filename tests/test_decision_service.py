import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundException
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun, UserDecision
from app.schemas.decision import DecisionBatchRequest, SingleDecisionRequest
from app.services.decisions import DecisionService


def _setup_test_rec(
    db: Session, title: str = "Inception", media_type: str = "movie"
) -> Recommendation:
    media = MediaItem(
        media_type=media_type,
        title=title,
        year=2010,
        tmdb_id=27205,
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
        match_score=91.0,
        confidence=0.85,
        reason="Mind-bending heist thriller.",
        status="pending",
    )
    db.add(rec)
    db.commit()
    return rec


def test_record_decision_accept(db_session: Session):
    rec = _setup_test_rec(db_session)
    service = DecisionService(db_session=db_session)

    req = DecisionBatchRequest(
        decisions=[
            SingleDecisionRequest(recommendation_id=rec.id, decision="accept", note="Must watch")
        ]
    )
    res = service.record_decisions(req)

    assert res.processed_count == 1
    assert len(res.decisions) == 1
    assert res.decisions[0].decision == "accept"
    assert res.decisions[0].note == "Must watch"
    assert res.decisions[0].media_title == "Inception"

    # Verify DB state
    db_session.refresh(rec)
    assert rec.status == "accepted"

    dec_row = db_session.scalar(
        select(UserDecision).where(UserDecision.recommendation_id == rec.id)
    )
    assert dec_row is not None
    assert dec_row.decision == "accept"


def test_record_decision_reject(db_session: Session):
    rec = _setup_test_rec(db_session)
    service = DecisionService(db_session=db_session)

    req = DecisionBatchRequest(
        decisions=[
            SingleDecisionRequest(
                recommendation_id=rec.id, decision="reject", note="Not interested"
            )
        ]
    )
    res = service.record_decisions(req)

    assert res.processed_count == 1
    db_session.refresh(rec)
    assert rec.status == "rejected"


def test_record_decision_seen(db_session: Session):
    rec = _setup_test_rec(db_session)
    service = DecisionService(db_session=db_session)

    req = DecisionBatchRequest(
        decisions=[SingleDecisionRequest(recommendation_id=rec.id, decision="seen")]
    )
    res = service.record_decisions(req)

    assert res.processed_count == 1
    db_session.refresh(rec)
    assert rec.status == "seen"

    # Verify WatchHistory marked as completed
    history = db_session.scalar(
        select(WatchHistory).where(WatchHistory.media_item_id == rec.media_item_id)
    )
    assert history is not None
    assert history.status == "completed"


def test_record_decision_later(db_session: Session):
    rec = _setup_test_rec(db_session)
    service = DecisionService(db_session=db_session)

    req = DecisionBatchRequest(
        decisions=[SingleDecisionRequest(recommendation_id=rec.id, decision="later")]
    )
    res = service.record_decisions(req)

    assert res.processed_count == 1
    db_session.refresh(rec)
    assert rec.status == "pending"


def test_record_decisions_batch(db_session: Session):
    rec1 = _setup_test_rec(db_session, title="Interstellar")
    rec2 = _setup_test_rec(db_session, title="Memento")
    service = DecisionService(db_session=db_session)

    req = DecisionBatchRequest(
        decisions=[
            SingleDecisionRequest(recommendation_id=rec1.id, decision="accept"),
            SingleDecisionRequest(recommendation_id=rec2.id, decision="reject"),
        ]
    )
    res = service.record_decisions(req)

    assert res.processed_count == 2
    db_session.refresh(rec1)
    db_session.refresh(rec2)
    assert rec1.status == "accepted"
    assert rec2.status == "rejected"


def test_record_decision_not_found(db_session: Session):
    service = DecisionService(db_session=db_session)
    req = DecisionBatchRequest(
        decisions=[SingleDecisionRequest(recommendation_id=99999, decision="accept")]
    )
    with pytest.raises(NotFoundException):
        service.record_decisions(req)


def test_list_decisions(db_session: Session):
    rec1 = _setup_test_rec(db_session, title="Oppenheimer")
    rec2 = _setup_test_rec(db_session, title="Tenet")
    service = DecisionService(db_session=db_session)

    service.record_decisions(
        DecisionBatchRequest(
            decisions=[
                SingleDecisionRequest(recommendation_id=rec1.id, decision="accept"),
                SingleDecisionRequest(recommendation_id=rec2.id, decision="reject"),
            ]
        )
    )

    all_decisions = service.list_decisions()
    assert len(all_decisions) >= 2

    accept_only = service.list_decisions(decision_filter="accept")
    assert any(d.recommendation_id == rec1.id for d in accept_only)
    assert all(d.decision == "accept" for d in accept_only)
