import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidStateException, NotFoundException
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.gemini import GeminiLLMClient
from app.models.history import WatchHistory
from app.models.media import MediaItem
from app.models.recommendation import Recommendation, RecommendationRun, UserDecision
from app.models.taste import TasteProfile
from app.schemas.recommendation import (
    CandidateItem,
    LLMEvaluationBatchResponse,
    LLMRecommendationEvaluation,
    RecommendationRead,
    RecommendationRunCreateRequest,
    RecommendationRunRead,
)
from app.schemas.taste import TasteProfileContent
from app.services.discovery import DiscoveryService

logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    """Normalizes title for fuzzy comparison (lowercase, alphanumeric only)."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


class AntiRecommendationFilter:
    """Excludes items already watched, on Plan to Watch, previously rejected,

    or recently recommended from candidate pools.
    """

    def __init__(
        self,
        known_tmdb_ids: Set[int],
        known_titles_years: Set[Tuple[str, Optional[int]]],
        rejected_tmdb_ids: Set[int],
        rejected_titles: Set[str],
        recent_recommended_tmdb_ids: Set[int],
        exclude_animation: bool = False,
    ):
        self.known_tmdb_ids = known_tmdb_ids
        self.known_titles_years = known_titles_years
        self.rejected_tmdb_ids = rejected_tmdb_ids
        self.rejected_titles = rejected_titles
        self.recent_recommended_tmdb_ids = recent_recommended_tmdb_ids
        self.exclude_animation = exclude_animation

    @classmethod
    def load_from_db(
        cls,
        db: Session,
        exclude_animation: bool = False,
        recent_days: int = 28,
    ) -> "AntiRecommendationFilter":
        """Loads all exclusion criteria directly from the SQLite database."""
        # 1. Watched and Plan to Watch items
        stmt_history = select(MediaItem.tmdb_id, MediaItem.title, MediaItem.year).join(
            WatchHistory, MediaItem.id == WatchHistory.media_item_id
        )
        history_rows = db.execute(stmt_history).all()

        known_tmdb_ids: Set[int] = {r[0] for r in history_rows if r[0]}
        known_titles_years: Set[Tuple[str, Optional[int]]] = {
            (normalize_title(r[1]), r[2]) for r in history_rows if r[1]
        }

        # 2. Rejected recommendations or decisions
        stmt_rejected_recs = (
            select(MediaItem.tmdb_id, MediaItem.title)
            .join(Recommendation, MediaItem.id == Recommendation.media_item_id)
            .where(Recommendation.status == "rejected")
        )
        rejected_rec_rows = db.execute(stmt_rejected_recs).all()

        stmt_rejected_decisions = (
            select(MediaItem.tmdb_id, MediaItem.title)
            .join(Recommendation, MediaItem.id == Recommendation.media_item_id)
            .join(UserDecision, Recommendation.id == UserDecision.recommendation_id)
            .where(UserDecision.decision == "reject")
        )
        rejected_dec_rows = db.execute(stmt_rejected_decisions).all()

        rejected_rows = list(rejected_rec_rows) + list(rejected_dec_rows)
        rejected_tmdb_ids: Set[int] = {r[0] for r in rejected_rows if r[0]}
        rejected_titles: Set[str] = {normalize_title(r[1]) for r in rejected_rows if r[1]}

        # 3. Recently recommended titles (to prevent repeating weekly)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=recent_days)
        stmt_recent = (
            select(MediaItem.tmdb_id)
            .join(Recommendation, MediaItem.id == Recommendation.media_item_id)
            .where(Recommendation.created_at >= cutoff_date)
        )
        recent_rows = db.execute(stmt_recent).scalars().all()
        recent_recommended_tmdb_ids: Set[int] = {tmdb_id for tmdb_id in recent_rows if tmdb_id}

        return cls(
            known_tmdb_ids=known_tmdb_ids,
            known_titles_years=known_titles_years,
            rejected_tmdb_ids=rejected_tmdb_ids,
            rejected_titles=rejected_titles,
            recent_recommended_tmdb_ids=recent_recommended_tmdb_ids,
            exclude_animation=exclude_animation,
        )

    def is_excluded(self, candidate: CandidateItem) -> Tuple[bool, Optional[str]]:
        """Checks if a candidate is excluded. Returns (is_excluded, reason)."""
        # Exclude animation if requested
        if self.exclude_animation and (
            16 in candidate.genre_ids or "Animation" in candidate.genres
        ):
            return True, "Excluded: Animation genre"

        # Check by TMDB ID in watched / Plan to Watch
        if candidate.tmdb_id in self.known_tmdb_ids:
            return True, "Already in watched history or Plan to Watch (TMDB ID match)"

        # Check by Title + Year in watched / Plan to Watch
        norm_title = normalize_title(candidate.title)
        if (norm_title, candidate.year) in self.known_titles_years:
            return True, f"Already in library (Title match: {candidate.title})"

        # Check rejected
        if candidate.tmdb_id in self.rejected_tmdb_ids or norm_title in self.rejected_titles:
            return True, "Previously rejected by user"

        # Check recently recommended
        if candidate.tmdb_id in self.recent_recommended_tmdb_ids:
            return True, "Recently recommended in a previous run"

        return False, None

    def filter(self, candidates: List[CandidateItem]) -> List[CandidateItem]:
        """Filters out excluded candidates."""
        accepted: List[CandidateItem] = []
        for cand in candidates:
            excluded, reason = self.is_excluded(cand)
            if not excluded:
                accepted.append(cand)
            else:
                logger.debug("Candidate excluded '%s': %s", cand.title, reason)
        return accepted


class RuleBasedRanker:
    """Computes a baseline heuristic score for candidates based on taste profile,

    TMDB metrics, and source strategies.
    """

    @staticmethod
    def score_candidate(candidate: CandidateItem, profile: TasteProfileContent) -> float:
        # 1. Base TMDB score (0-40 pts): vote_average + popularity
        base_score = (candidate.vote_average * 4.0) + min(candidate.popularity * 0.1, 10.0)

        # 2. Genre alignment (0-30 pts)
        cand_genres_lower = [g.lower() for g in candidate.genres]
        genre_score = 0.0
        for pref in profile.genres:
            if pref.name.lower() in cand_genres_lower:
                genre_score += pref.weight * pref.confidence * 15.0
        genre_score = min(genre_score, 30.0)

        # 3. Theme alignment (0-15 pts) in overview
        theme_score = 0.0
        overview_lower = (candidate.overview or "").lower()
        for theme in profile.themes:
            # Check key words from theme name
            keywords = [w for w in theme.name.lower().split() if len(w) > 3]
            if any(kw in overview_lower for kw in keywords):
                theme_score += theme.weight * 5.0
        theme_score = min(theme_score, 15.0)

        # 4. Director / Creator bonus (10 pts)
        director_score = 0.0
        if candidate.director_or_creator:
            dir_lower = candidate.director_or_creator.lower()
            if any(creator.lower() in dir_lower for creator in profile.directors_or_creators):
                director_score = 10.0

        # 5. Source strategy bonus (5 pts)
        strat_score = 5.0 if candidate.source_strategy == "similar_to_favorites" else 2.0

        # 6. Anti-preferences penalty
        anti_penalty = 0.0
        for anti in profile.anti_preferences:
            anti_keywords = [w for w in anti.lower().split() if len(w) > 3]
            if any(kw in overview_lower for kw in anti_keywords):
                anti_penalty += 15.0

        total_score = max(
            0.0,
            base_score
            + genre_score
            + theme_score
            + director_score
            + strat_score
            - anti_penalty,
        )
        return total_score

    def select_top_candidates(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
        movie_limit: int = 25,
        show_limit: int = 15,
    ) -> Tuple[List[CandidateItem], List[CandidateItem]]:
        """Scores all candidates and returns top movies and top shows for LLM evaluation."""
        movies = [c for c in candidates if c.media_type == "movie"]
        shows = [c for c in candidates if c.media_type == "show"]

        scored_movies = sorted(movies, key=lambda m: self.score_candidate(m, profile), reverse=True)
        scored_shows = sorted(shows, key=lambda s: self.score_candidate(s, profile), reverse=True)

        return scored_movies[:movie_limit], scored_shows[:show_limit]


class SemanticScorer:
    """Interacts with LLMProvider to evaluate semantic fit, reasons, and risks for candidates."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or GeminiLLMClient()

    def _create_prompt(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
    ) -> str:
        candidates_json = []
        for idx, cand in enumerate(candidates):
            candidates_json.append(
                {
                    "index": idx,
                    "title": cand.title,
                    "year": cand.year,
                    "media_type": cand.media_type,
                    "genres": cand.genres,
                    "director": cand.director_or_creator,
                    "overview": cand.overview,
                    "vote_average": cand.vote_average,
                }
            )

        profile_summary = {
            "summary": profile.summary,
            "preferred_genres": [f"{g.name} (wt: {g.weight})" for g in profile.genres],
            "themes": [t.name for t in profile.themes],
            "favored_directors": profile.directors_or_creators,
            "anti_preferences": profile.anti_preferences,
        }

        return f"""
Analyze the following media candidates and evaluate how well each fits the user's taste profile.
You MUST return a JSON object with an "evaluations" array.

User Taste Profile:
{json.dumps(profile_summary, ensure_ascii=False, indent=2)}

Candidates to evaluate:
{json.dumps(candidates_json, ensure_ascii=False, indent=2)}

Guidelines:
1. "candidate_index": Exact integer index of candidate from the list.
2. "match_score": Float 0 to 100 representing semantic fit with user profile.
3. "confidence": Float 0.0 to 1.0 reflecting confidence from metadata quality.
4. "positive_factors": 1 to 3 concise strings describing why this matches user taste.
5. "risks": 0 to 2 potential concerns or mismatch risks (or empty list if none).
6. "reason": A 1-2 sentence compelling Polish narrative explaining why this title fits.
"""

    async def evaluate_candidates(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
    ) -> Dict[int, LLMRecommendationEvaluation]:
        """Calls LLM to evaluate candidates and returns map of candidate_index -> evaluation."""
        if not candidates:
            return {}

        prompt = self._create_prompt(candidates, profile)
        system_instruction = (
            "You are a sophisticated cinematic taste analyzer and personal recommender. "
            "Output strictly valid JSON conforming to the requested schema. Do not invent metadata."
        )

        try:
            raw_response = await self.llm_provider.generate_structured(
                prompt=prompt,
                system_instruction=system_instruction,
            )
            parsed = LLMEvaluationBatchResponse.model_validate(raw_response)
            return {ev.candidate_index: ev for ev in parsed.evaluations}
        except Exception as e:
            logger.warning(
                "LLM evaluation failed or returned malformed JSON: %s. Using heuristic fallback.", e
            )
            # Fallback heuristic evaluations
            fallback_map: Dict[int, LLMRecommendationEvaluation] = {}
            for idx, cand in enumerate(candidates):
                rule_score = min(95.0, max(60.0, cand.vote_average * 10.0))
                genres_str = ", ".join(cand.genres[:2]) if cand.genres else "film"
                fallback_map[idx] = LLMRecommendationEvaluation(
                    candidate_index=idx,
                    match_score=rule_score,
                    confidence=0.7,
                    positive_factors=[f"Dopasowanie gatunkowe: {genres_str}"],
                    risks=[],
                    reason=(
                        f"Tytuł dopasowany do preferencji gatunkowych ({genres_str}) "
                        f"z oceną TMDB ({cand.vote_average})."
                    ),
                )
            return fallback_map


class DiversificationService:
    """Enforces diversity rules, director limits, and picks final recommended items."""

    @staticmethod
    def diversify(
        candidates_with_evals: List[Tuple[CandidateItem, LLMRecommendationEvaluation]],
        limit: int,
        max_per_director: int = 2,
    ) -> List[Tuple[CandidateItem, LLMRecommendationEvaluation]]:
        # Sort by match_score descending
        sorted_items = sorted(
            candidates_with_evals, key=lambda item: item[1].match_score, reverse=True
        )

        selected: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
        director_counts: Dict[str, int] = {}

        for cand, ev in sorted_items:
            director = cand.director_or_creator
            if director:
                if director_counts.get(director, 0) >= max_per_director:
                    continue

            selected.append((cand, ev))
            if director:
                director_counts[director] = director_counts.get(director, 0) + 1

            if len(selected) >= limit:
                break

        return selected


class RecommendationService:
    """Main domain service for running and managing recommendation generation runs."""

    def __init__(
        self,
        discovery_service: Optional[DiscoveryService] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.discovery = discovery_service or DiscoveryService()
        self.llm_provider = llm_provider or GeminiLLMClient()
        self.semantic_scorer = SemanticScorer(llm_provider=self.llm_provider)

    def get_active_profile(
        self, db: Session, force_version: Optional[str] = None
    ) -> Tuple[TasteProfile, TasteProfileContent]:
        """Fetches active taste profile from DB or a specific requested version."""
        if force_version:
            profile_model = db.execute(
                select(TasteProfile).where(TasteProfile.version == force_version)
            ).scalar_one_or_none()
            if not profile_model:
                raise NotFoundException(f"Taste profile version '{force_version}' not found.")
        else:
            profile_model = db.execute(
                select(TasteProfile).where(TasteProfile.active.is_(True))
            ).scalar_one_or_none()
            if not profile_model:
                raise InvalidStateException(
                    "No active taste profile found. Generate or activate a taste profile first."
                )

        content = TasteProfileContent.model_validate_json(profile_model.profile_json)
        return profile_model, content

    async def create_recommendation_run(
        self,
        db: Session,
        request: Optional[RecommendationRunCreateRequest] = None,
    ) -> RecommendationRun:
        """Executes full recommendation generation pipeline and records run to SQLite."""
        req = request or RecommendationRunCreateRequest()
        profile_model, profile_content = self.get_active_profile(
            db, force_version=req.force_profile_version
        )

        # 1. Initialize pending run record
        run = RecommendationRun(
            status="pending",
            profile_version=profile_model.version,
            model_provider=self.llm_provider.provider_name,
            model_name=self.llm_provider.model_name,
            parameters_json=json.dumps(req.model_dump(), ensure_ascii=False),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            # 2. Check animation exclusion from anti-preferences or request
            exclude_anim = any("anim" in g.lower() for g in req.exclude_genres) or any(
                "anim" in a.lower() for a in profile_content.anti_preferences
            )

            # 3. Discover candidates from TMDB
            candidates = await self.discovery.discover_candidates(
                db=db,
                profile=profile_content,
                exclude_genres=req.exclude_genres,
            )

            # 4. Anti-recommendation filtering
            anti_filter = AntiRecommendationFilter.load_from_db(
                db=db, exclude_animation=exclude_anim
            )
            filtered_candidates = anti_filter.filter(candidates)

            # 5. Rule-based pre-ranking
            ranker = RuleBasedRanker()
            top_movies, top_shows = ranker.select_top_candidates(
                candidates=filtered_candidates,
                profile=profile_content,
                movie_limit=25,
                show_limit=15,
            )

            # 6. LLM Semantic evaluation
            all_top_candidates = top_movies + top_shows
            evaluations_map = await self.semantic_scorer.evaluate_candidates(
                candidates=all_top_candidates,
                profile=profile_content,
            )

            evaluated_movies: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
            for idx, cand in enumerate(top_movies):
                ev = evaluations_map.get(idx)
                if not ev:
                    g_sub = ", ".join(cand.genres[:2])
                    ev = LLMRecommendationEvaluation(
                        candidate_index=idx,
                        match_score=min(95.0, max(60.0, cand.vote_average * 10.0)),
                        confidence=0.7,
                        positive_factors=[f"Dopasowanie gatunkowe: {g_sub}"],
                        risks=[],
                        reason=(
                            f"Film polecany na podstawie profilu gustu "
                            f"oraz oceny TMDB ({cand.vote_average})."
                        ),
                    )
                evaluated_movies.append((cand, ev))

            evaluated_shows: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
            for idx, cand in enumerate(top_shows):
                show_idx = len(top_movies) + idx
                ev = evaluations_map.get(show_idx)
                if not ev:
                    g_sub = ", ".join(cand.genres[:2])
                    ev = LLMRecommendationEvaluation(
                        candidate_index=show_idx,
                        match_score=min(95.0, max(60.0, cand.vote_average * 10.0)),
                        confidence=0.7,
                        positive_factors=[f"Dopasowanie gatunkowe: {g_sub}"],
                        risks=[],
                        reason=(
                            f"Serial polecany na podstawie profilu gustu "
                            f"oraz oceny TMDB ({cand.vote_average})."
                        ),
                    )
                evaluated_shows.append((cand, ev))

            # 7. Diversification & final selection (10 movies, 5 shows)
            final_movies = DiversificationService.diversify(
                evaluated_movies, limit=req.movie_limit, max_per_director=2
            )
            final_shows = DiversificationService.diversify(
                evaluated_shows, limit=req.show_limit, max_per_director=2
            )
            final_selection = final_movies + final_shows

            # 8. Save/Upsert MediaItems and Recommendations in SQLite
            for cand, ev in final_selection:
                # Find or create MediaItem
                media_item = db.execute(
                    select(MediaItem).where(
                        MediaItem.media_type == cand.media_type,
                        MediaItem.tmdb_id == cand.tmdb_id,
                    )
                ).scalar_one_or_none()

                if not media_item:
                    media_item = MediaItem(
                        media_type=cand.media_type,
                        title=cand.title,
                        year=cand.year,
                        tmdb_id=cand.tmdb_id,
                        imdb_id=cand.imdb_id,
                        metadata_json=json.dumps(
                            {
                                "overview": cand.overview,
                                "genres": cand.genres,
                                "director_or_creator": cand.director_or_creator,
                                "poster_path": cand.poster_path,
                                "vote_average": cand.vote_average,
                                "vote_count": cand.vote_count,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    db.add(media_item)
                    db.flush()

                # Add Recommendation
                recommendation = Recommendation(
                    run_id=run.id,
                    media_item_id=media_item.id,
                    match_score=ev.match_score,
                    confidence=ev.confidence,
                    reason=ev.reason,
                    positive_factors_json=json.dumps(ev.positive_factors, ensure_ascii=False),
                    risks_json=json.dumps(ev.risks, ensure_ascii=False),
                    status="pending",
                )
                db.add(recommendation)

            # 9. Update run status to completed
            run.status = "completed"
            run.summary = (
                f"Wygenerowano pomyślnie {len(final_movies)} filmów i {len(final_shows)} seriali "
                f"w oparciu o profil {profile_model.version}."
            )
            db.commit()
            db.refresh(run)
            return run

        except Exception as e:
            db.rollback()
            run.status = "failed"
            run.summary = f"Błąd generowania rekomendacji: {str(e)}"
            db.commit()
            logger.exception("Failed recommendation run %d: %s", run.id, e)
            raise

    def get_run(self, db: Session, run_id: int) -> RecommendationRun:
        """Retrieves a recommendation run by ID."""
        run = db.execute(
            select(RecommendationRun).where(RecommendationRun.id == run_id)
        ).scalar_one_or_none()
        if not run:
            raise NotFoundException(f"Recommendation run #{run_id} not found.")
        return run

    def list_runs(
        self, db: Session, limit: int = 20, offset: int = 0
    ) -> List[RecommendationRun]:
        """Lists historical recommendation runs."""
        stmt = (
            select(RecommendationRun)
            .order_by(desc(RecommendationRun.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def to_read_schema(run: RecommendationRun) -> RecommendationRunRead:
        """Converts SQLAlchemy RecommendationRun model into Pydantic RecommendationRunRead."""
        parameters = {}
        if run.parameters_json:
            try:
                parameters = json.loads(run.parameters_json)
            except Exception:
                pass

        recommendations_read: List[RecommendationRead] = []
        for rec in run.recommendations:
            pos_factors = []
            if rec.positive_factors_json:
                try:
                    pos_factors = json.loads(rec.positive_factors_json)
                except Exception:
                    pass

            risks = []
            if rec.risks_json:
                try:
                    risks = json.loads(rec.risks_json)
                except Exception:
                    pass

            recommendations_read.append(
                RecommendationRead(
                    id=rec.id,
                    run_id=rec.run_id,
                    media_item_id=rec.media_item_id,
                    match_score=rec.match_score,
                    confidence=rec.confidence,
                    reason=rec.reason,
                    positive_factors=pos_factors,
                    risks=risks,
                    status=rec.status,
                    created_at=rec.created_at,
                    media_item=rec.media_item,
                )
            )

        return RecommendationRunRead(
            id=run.id,
            status=run.status,
            created_at=run.created_at,
            profile_version=run.profile_version,
            model_provider=run.model_provider,
            model_name=run.model_name,
            summary=run.summary,
            parameters=parameters,
            recommendations=recommendations_read,
        )
