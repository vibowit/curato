import asyncio
import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    InvalidStateException,
    NotFoundException,
    UpstreamErrorException,
)
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
    MediaItemSummary,
    RecommendationRead,
    RecommendationRunCreateRequest,
    RecommendationRunRead,
    TrailerResponse,
)
from app.schemas.taste import TasteProfileContent
from app.services.discovery import DiscoveryService
from app.services.locale import locale_service

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

        # 2. Rejected recommendations or decisions (including items marked as seen)
        stmt_rejected_recs = (
            select(MediaItem.tmdb_id, MediaItem.title)
            .join(Recommendation, MediaItem.id == Recommendation.media_item_id)
            .where(Recommendation.status.in_(["rejected", "seen"]))
        )
        rejected_rec_rows = db.execute(stmt_rejected_recs).all()

        stmt_rejected_decisions = (
            select(MediaItem.tmdb_id, MediaItem.title)
            .join(Recommendation, MediaItem.id == Recommendation.media_item_id)
            .join(UserDecision, Recommendation.id == UserDecision.recommendation_id)
            .where(UserDecision.decision.in_(["reject", "seen"]))
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
            base_score + genre_score + theme_score + director_score + strat_score - anti_penalty,
        )
        return total_score

    @staticmethod
    def score_wildcard_candidate(candidate: CandidateItem, profile: TasteProfileContent) -> float:
        # 1. Base TMDB score (vote_average * 8 + popularity)
        base_score = (candidate.vote_average * 8.0) + min(candidate.popularity * 0.1, 15.0)

        # 2. Vote count reliability bonus (0-10 pts)
        vote_bonus = min(float(candidate.vote_count) / 100.0, 10.0)

        # 3. Anti-preferences penalty
        anti_penalty = 0.0
        overview_lower = (candidate.overview or "").lower()
        for anti in profile.anti_preferences:
            anti_keywords = [w for w in anti.lower().split() if len(w) > 3]
            if any(kw in overview_lower for kw in anti_keywords):
                anti_penalty += 30.0

        return max(0.0, base_score + vote_bonus - anti_penalty)

    def select_top_candidates(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
        movie_limit: int = 25,
        show_limit: int = 15,
        wildcard_movie_limit: int = 5,
        wildcard_show_limit: int = 4,
    ) -> Tuple[List[CandidateItem], List[CandidateItem]]:
        """Scores all candidates and returns top movies and top shows for LLM evaluation,

        ensuring separate, dedicated candidate pools for profile items and wildcard items.
        """
        profile_movies = [c for c in candidates if c.media_type == "movie" and not c.is_wildcard]
        profile_shows = [c for c in candidates if c.media_type == "show" and not c.is_wildcard]

        wildcard_movies = [c for c in candidates if c.media_type == "movie" and c.is_wildcard]
        wildcard_shows = [c for c in candidates if c.media_type == "show" and c.is_wildcard]

        scored_prof_movies = sorted(
            profile_movies, key=lambda m: self.score_candidate(m, profile), reverse=True
        )
        scored_prof_shows = sorted(
            profile_shows, key=lambda s: self.score_candidate(s, profile), reverse=True
        )

        scored_wild_movies = sorted(
            wildcard_movies, key=lambda m: self.score_wildcard_candidate(m, profile), reverse=True
        )
        scored_wild_shows = sorted(
            wildcard_shows, key=lambda s: self.score_wildcard_candidate(s, profile), reverse=True
        )

        selected_movies = (
            scored_prof_movies[:movie_limit] + scored_wild_movies[:wildcard_movie_limit]
        )
        selected_shows = (
            scored_prof_shows[:show_limit] + scored_wild_shows[:wildcard_show_limit]
        )

        return selected_movies, selected_shows


class SemanticScorer:
    """Interacts with LLMProvider to evaluate semantic fit, reasons, and risks for candidates."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or GeminiLLMClient()

    def _create_prompt(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
        language: Optional[str] = None,
    ) -> Tuple[str, str]:
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
                    "is_wildcard": cand.is_wildcard,
                }
            )

        profile_summary = {
            "summary": profile.summary,
            "preferred_genres": [f"{g.name} (wt: {g.weight})" for g in profile.genres],
            "themes": [t.name for t in profile.themes],
            "favored_directors": profile.directors_or_creators,
            "anti_preferences": profile.anti_preferences,
        }

        lang = language or settings.DEFAULT_LANGUAGE
        prompts = locale_service.get_prompt_templates(lang)
        rec_prompts = prompts.get("recommendations", {})

        system_instruction = rec_prompts.get(
            "system_instruction",
            (
                "You are a sophisticated cinematic taste analyzer and personal recommender. "
                "Output strictly valid JSON conforming to the requested schema. "
                "Do not invent metadata."
            ),
        )

        reason_instr = rec_prompts.get(
            "reason_instruction",
            "1-2 sentence compelling narrative explaining why this title fits.",
        )
        pos_instr = rec_prompts.get(
            "positive_factors_instruction",
            "1 to 3 concise strings describing why this matches user taste.",
        )
        risks_instr = rec_prompts.get(
            "risks_instruction",
            "0 to 2 potential concerns or mismatch risks (or empty list if none).",
        )

        n = len(candidates)
        prompt = f"""
Analyze the following media candidates and evaluate how well each fits the user's taste profile.
You MUST return a JSON object with an "evaluations" array containing exactly {n} items.
Every candidate from index 0 to {n-1} must have an evaluation.

User Taste Profile:
{json.dumps(profile_summary, ensure_ascii=False, indent=2)}

Candidates to evaluate ({n} items):
{json.dumps(candidates_json, ensure_ascii=False, indent=2)}

Guidelines:
1. "candidate_index": Exact integer index of candidate from the list (0 to {n-1}).
2. "match_score": Float 0 to 100 representing semantic fit with user profile.
   For candidates with "is_wildcard": true, match_score represents breakthrough
   appeal and quality as a horizon-broadening pick (0 to 100).
3. "confidence": Float 0.0 to 1.0 reflecting confidence from metadata quality.
4. "positive_factors": {pos_instr}
5. "risks": {risks_instr}
6. "reason": {reason_instr}
   For candidates with "is_wildcard": true, the reason should compellingly explain why
   it is worth taking a chance on this title despite lying outside typical profile genres.
"""
        return prompt, system_instruction

    async def evaluate_candidates(
        self,
        candidates: List[CandidateItem],
        profile: TasteProfileContent,
        language: Optional[str] = None,
    ) -> Dict[int, LLMRecommendationEvaluation]:
        """Calls LLM to evaluate candidates and returns map of candidate_index -> evaluation."""
        if not candidates:
            return {}

        prompt, system_instruction = self._create_prompt(candidates, profile, language=language)

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
                if cand.is_wildcard:
                    if language == "en":
                        reason = (
                            f"Surprise Me selection: critically acclaimed title ({genres_str}) "
                            f"with TMDB rating {cand.vote_average} to broaden your horizons."
                        )
                        pos = ["Surprise Me / Wildcard", f"TMDB rating: {cand.vote_average}"]
                    else:
                        reason = (
                            f"Tytuł 'Zaskocz mnie': wysoko oceniany ({genres_str}) "
                            f"z oceną TMDB {cand.vote_average}, na poszerzenie horyzontów."
                        )
                        pos = ["Kategoria 'Zaskocz mnie'", f"Ocena TMDB: {cand.vote_average}"]
                else:
                    if language == "en":
                        reason = (
                            f"Title matching your taste profile ({genres_str}) "
                            f"with TMDB rating {cand.vote_average}."
                        )
                        pos = [f"Genre alignment: {genres_str}"]
                    else:
                        reason = (
                            f"Tytuł dopasowany do preferencji gatunkowych ({genres_str}) "
                            f"z oceną TMDB ({cand.vote_average})."
                        )
                        pos = [f"Dopasowanie gatunkowe: {genres_str}"]

                fallback_map[idx] = LLMRecommendationEvaluation(
                    candidate_index=idx,
                    match_score=rule_score,
                    confidence=0.85,
                    positive_factors=pos,
                    risks=[],
                    reason=reason,
                )
            return fallback_map


class DiversificationService:
    """Enforces diversity rules, director limits, and picks final recommended items."""

    @staticmethod
    def diversify(
        candidates_with_evals: List[Tuple[CandidateItem, LLMRecommendationEvaluation]],
        limit: int,
        max_per_director: int = 2,
        include_wildcards: bool = True,
    ) -> List[Tuple[CandidateItem, LLMRecommendationEvaluation]]:
        if limit <= 0:
            return []

        profile_items = sorted(
            [item for item in candidates_with_evals if not item[0].is_wildcard],
            key=lambda item: item[1].match_score,
            reverse=True,
        )
        wildcard_items = sorted(
            [item for item in candidates_with_evals if item[0].is_wildcard],
            key=lambda item: item[1].match_score,
            reverse=True,
        )

        should_pick_wildcard = include_wildcards and limit >= 2 and len(wildcard_items) > 0
        target_profile_count = (limit - 1) if should_pick_wildcard else limit

        selected: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
        director_counts: Dict[str, int] = {}

        # 1. Select profile items
        for cand, ev in profile_items:
            director = cand.director_or_creator
            if director and director_counts.get(director, 0) >= max_per_director:
                continue

            selected.append((cand, ev))
            if director:
                director_counts[director] = director_counts.get(director, 0) + 1

            if len(selected) >= target_profile_count:
                break

        # 2. Select wildcard item if requested and available
        if should_pick_wildcard:
            chosen_wildcard = None
            for cand, ev in wildcard_items:
                director = cand.director_or_creator
                if director and director_counts.get(director, 0) >= max_per_director:
                    continue
                chosen_wildcard = (cand, ev)
                if director:
                    director_counts[director] = director_counts.get(director, 0) + 1
                break

            if chosen_wildcard:
                selected.append(chosen_wildcard)

        # 3. Backfill if still under limit
        if len(selected) < limit:
            selected_ids = {cand.tmdb_id for cand, _ in selected}
            for pool in [profile_items, wildcard_items]:
                for cand, ev in pool:
                    if cand.tmdb_id in selected_ids:
                        continue
                    director = cand.director_or_creator
                    if director and director_counts.get(director, 0) >= max_per_director:
                        continue
                    selected.append((cand, ev))
                    selected_ids.add(cand.tmdb_id)
                    if director:
                        director_counts[director] = director_counts.get(director, 0) + 1
                    if len(selected) >= limit:
                        break
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
            target_lang = req.language or settings.DEFAULT_LANGUAGE

            # 3. Discover candidates from TMDB
            candidates = await self.discovery.discover_candidates(
                db=db,
                profile=profile_content,
                exclude_genres=req.exclude_genres,
                language=target_lang,
            )
            if not candidates:
                raise UpstreamErrorException(
                    message=(
                        "Nie udało się pobrać kandydatów z TMDB. "
                        "Sprawdź połączenie z Internetem oraz konfigurację TMDB_API_KEY."
                    )
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

            # 6. LLM Semantic evaluation (evaluated separately to guarantee full coverage)
            movie_evals_map = await self.semantic_scorer.evaluate_candidates(
                candidates=top_movies,
                profile=profile_content,
                language=target_lang,
            )
            show_evals_map = await self.semantic_scorer.evaluate_candidates(
                candidates=top_shows,
                profile=profile_content,
                language=target_lang,
            )

            evaluated_movies: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
            for idx, cand in enumerate(top_movies):
                ev = movie_evals_map.get(idx)
                if not ev:
                    g_sub = ", ".join(cand.genres[:2]) if cand.genres else "film"
                    if cand.is_wildcard:
                        if target_lang == "en":
                            pos_factors = [
                                "Surprise Me / Wildcard",
                                f"TMDB rating: {cand.vote_average}",
                            ]
                            fallback_reason = (
                                f"Surprise Me selection: highly acclaimed title ({g_sub}) "
                                f"with TMDB rating {cand.vote_average} to broaden your horizons."
                            )
                        else:
                            pos_factors = [
                                "Kategoria 'Zaskocz mnie'",
                                f"Ocena TMDB: {cand.vote_average}",
                            ]
                            fallback_reason = (
                                f"Film z kategorii 'Zaskocz mnie': tytuł ({g_sub}) z oceną "
                                f"TMDB {cand.vote_average}, wybrany na poszerzenie horyzontów."
                            )
                    else:
                        if target_lang == "en":
                            pos_factors = [f"Genre alignment: {g_sub}"]
                            fallback_reason = (
                                "Recommended title based on taste profile and "
                                f"TMDB rating ({cand.vote_average})."
                            )
                        else:
                            pos_factors = [f"Dopasowanie gatunkowe: {g_sub}"]
                            fallback_reason = (
                                "Film polecany na podstawie profilu gustu oraz "
                                f"oceny TMDB ({cand.vote_average})."
                            )
                    ev = LLMRecommendationEvaluation(
                        candidate_index=idx,
                        match_score=min(95.0, max(60.0, cand.vote_average * 10.0)),
                        confidence=0.85,
                        positive_factors=pos_factors,
                        risks=[],
                        reason=fallback_reason,
                    )
                evaluated_movies.append((cand, ev))

            evaluated_shows: List[Tuple[CandidateItem, LLMRecommendationEvaluation]] = []
            for idx, cand in enumerate(top_shows):
                ev = show_evals_map.get(idx)
                if not ev:
                    g_sub = ", ".join(cand.genres[:2]) if cand.genres else "serial"
                    if cand.is_wildcard:
                        if target_lang == "en":
                            pos_factors = [
                                "Surprise Me / Wildcard",
                                f"TMDB rating: {cand.vote_average}",
                            ]
                            fallback_reason = (
                                f"Surprise Me selection: highly acclaimed TV show ({g_sub}) "
                                f"with TMDB rating {cand.vote_average} to broaden your horizons."
                            )
                        else:
                            pos_factors = [
                                "Kategoria 'Zaskocz mnie'",
                                f"Ocena TMDB: {cand.vote_average}",
                            ]
                            fallback_reason = (
                                f"Serial z kategorii 'Zaskocz mnie': tytuł ({g_sub}) z oceną "
                                f"TMDB {cand.vote_average}, wybrany na poszerzenie horyzontów."
                            )
                    else:
                        if target_lang == "en":
                            pos_factors = [f"Genre alignment: {g_sub}"]
                            fallback_reason = (
                                "Recommended TV show based on taste profile and "
                                f"TMDB rating ({cand.vote_average})."
                            )
                        else:
                            pos_factors = [f"Dopasowanie gatunkowe: {g_sub}"]
                            fallback_reason = (
                                "Serial polecany na podstawie profilu gustu oraz "
                                f"oceny TMDB ({cand.vote_average})."
                            )
                    ev = LLMRecommendationEvaluation(
                        candidate_index=idx,
                        match_score=min(95.0, max(60.0, cand.vote_average * 10.0)),
                        confidence=0.85,
                        positive_factors=pos_factors,
                        risks=[],
                        reason=fallback_reason,
                    )
                evaluated_shows.append((cand, ev))

            # 7. Diversification & final selection (10 movies, 5 shows)
            final_movies = DiversificationService.diversify(
                evaluated_movies,
                limit=req.movie_limit,
                max_per_director=2,
                include_wildcards=req.include_wildcards,
            )
            final_shows = DiversificationService.diversify(
                evaluated_shows,
                limit=req.show_limit,
                max_per_director=2,
                include_wildcards=req.include_wildcards,
            )
            final_selection = final_movies + final_shows

            # Fetch trailers for final selection concurrently
            sem_trailers = asyncio.Semaphore(5)

            async def hydrate_trailer(cand: CandidateItem) -> None:
                if not cand.tmdb_id:
                    return
                async with sem_trailers:
                    try:
                        if cand.media_type == "movie":
                            vid_res = await self.discovery.tmdb.get_movie_videos(cand.tmdb_id)
                        else:
                            vid_res = await self.discovery.tmdb.get_show_videos(cand.tmdb_id)
                        best = self.discovery.tmdb.extract_best_trailer(vid_res)
                        if best:
                            cand.trailer_key = best["trailer_key"]
                            cand.trailer_url = best["trailer_url"]
                    except Exception as e:
                        logger.debug(
                            "Failed fetching trailer for %s (%d): %s", cand.title, cand.tmdb_id, e
                        )

            await asyncio.gather(*(hydrate_trailer(cand) for cand, _ in final_selection))

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
                                "trailer_key": cand.trailer_key,
                                "trailer_url": cand.trailer_url,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    db.add(media_item)
                    db.flush()
                else:
                    # Update metadata_json if trailer is newly discovered
                    if cand.trailer_key:
                        meta = {}
                        if media_item.metadata_json:
                            try:
                                meta = json.loads(media_item.metadata_json)
                            except Exception:
                                meta = {}
                        if not meta.get("trailer_key"):
                            meta["trailer_key"] = cand.trailer_key
                            meta["trailer_url"] = cand.trailer_url
                            media_item.metadata_json = json.dumps(meta, ensure_ascii=False)

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
                    is_wildcard=cand.is_wildcard,
                )
                db.add(recommendation)

            # 9. Update run status to completed
            run.status = "completed"
            if target_lang == "en":
                run.summary = (
                    f"Successfully generated {len(final_movies)} movies "
                    f"and {len(final_shows)} TV shows based on taste profile "
                    f"{profile_model.version}."
                )
            else:
                run.summary = (
                    f"Wygenerowano pomyślnie {len(final_movies)} filmów i "
                    f"{len(final_shows)} seriali w oparciu o profil "
                    f"{profile_model.version}."
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

    def get_latest_run(self, db: Session) -> Optional[RecommendationRun]:
        """Retrieves the most recent recommendation run."""
        stmt = select(RecommendationRun).order_by(desc(RecommendationRun.created_at)).limit(1)
        return db.execute(stmt).scalar_one_or_none()

    def list_runs(self, db: Session, limit: int = 20, offset: int = 0) -> List[RecommendationRun]:
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

            media_summary = None
            trailer_key = None
            trailer_url = None
            if rec.media_item:
                poster_path = None
                vote_avg = None
                if rec.media_item.metadata_json:
                    try:
                        meta = json.loads(rec.media_item.metadata_json)
                        poster_path = meta.get("poster_path")
                        trailer_key = meta.get("trailer_key")
                        trailer_url = meta.get("trailer_url")
                        raw_vote = meta.get("vote_average")
                        if raw_vote is not None:
                            vote_avg = float(raw_vote)
                    except Exception:
                        pass
                media_summary = MediaItemSummary(
                    id=rec.media_item.id,
                    media_type=rec.media_item.media_type,
                    title=rec.media_item.title,
                    year=rec.media_item.year,
                    tmdb_id=rec.media_item.tmdb_id,
                    simkl_id=rec.media_item.simkl_id,
                    imdb_id=rec.media_item.imdb_id,
                    metadata_json=rec.media_item.metadata_json,
                    poster_path=poster_path,
                    trailer_key=trailer_key,
                    trailer_url=trailer_url,
                    vote_average=vote_avg,
                )

            latest_decision = None
            if getattr(rec, "decisions", None) and len(rec.decisions) > 0:
                latest_decision = rec.decisions[-1].decision

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
                    is_wildcard=getattr(rec, "is_wildcard", False),
                    latest_decision=latest_decision,
                    created_at=rec.created_at,
                    trailer_key=trailer_key,
                    trailer_url=trailer_url,
                    media_item=media_summary,
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

    async def get_or_fetch_trailer(self, db: Session, recommendation_id: int) -> TrailerResponse:
        """Retrieves or dynamically fetches the YouTube trailer for a recommendation."""
        rec = db.execute(
            select(Recommendation).where(Recommendation.id == recommendation_id)
        ).scalar_one_or_none()
        if not rec:
            raise NotFoundException(f"Recommendation #{recommendation_id} not found.")

        media_item = rec.media_item
        title = media_item.title if media_item else "Unknown"
        year = media_item.year if media_item else None

        # Build YouTube search query fallback
        search_query = f"{title} {year or ''} official trailer".strip()
        fallback_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(search_query)}"
        )

        if not media_item:
            return TrailerResponse(
                recommendation_id=rec.id,
                title=title,
                year=year,
                trailer_key=None,
                trailer_url=None,
                fallback_search_url=fallback_url,
            )

        # Check existing metadata
        metadata: Dict[str, Any] = {}
        if media_item.metadata_json:
            try:
                metadata = json.loads(media_item.metadata_json)
            except Exception:
                metadata = {}

        if metadata.get("trailer_key"):
            return TrailerResponse(
                recommendation_id=rec.id,
                title=title,
                year=year,
                trailer_key=metadata.get("trailer_key"),
                trailer_url=metadata.get("trailer_url"),
                fallback_search_url=fallback_url,
            )

        # Not present in metadata, fetch from TMDB if tmdb_id is available
        if media_item.tmdb_id:
            try:
                if media_item.media_type == "movie":
                    vid_res = await self.discovery.tmdb.get_movie_videos(media_item.tmdb_id)
                else:
                    vid_res = await self.discovery.tmdb.get_show_videos(media_item.tmdb_id)
                best = self.discovery.tmdb.extract_best_trailer(vid_res)
                if best:
                    metadata["trailer_key"] = best["trailer_key"]
                    metadata["trailer_url"] = best["trailer_url"]
                    media_item.metadata_json = json.dumps(metadata, ensure_ascii=False)
                    db.commit()
                    db.refresh(media_item)
                    return TrailerResponse(
                        recommendation_id=rec.id,
                        title=title,
                        year=year,
                        trailer_key=best["trailer_key"],
                        trailer_url=best["trailer_url"],
                        fallback_search_url=fallback_url,
                    )
            except Exception as e:
                logger.warning(
                    "Failed on-demand trailer fetch for recommendation %d (TMDB %d): %s",
                    recommendation_id,
                    media_item.tmdb_id,
                    e,
                )

        return TrailerResponse(
            recommendation_id=rec.id,
            title=title,
            year=year,
            trailer_key=None,
            trailer_url=None,
            fallback_search_url=fallback_url,
        )
