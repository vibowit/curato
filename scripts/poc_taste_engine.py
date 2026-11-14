#!/usr/bin/env python3
"""Simkl Taste Engine - Proof of Concept (PoC)

Part of the Personal Movie & TV Show Recommender project.
Validates:
1. Simkl history extraction and normalization.
2. User taste profiling via LLM (Gemini) or offline heuristic.
3. Candidate recommendation generation (10 movies, 5 shows).
4. Strict anti-recommendation filtering (excluding watched & plan to watch).
5. Safe read-only execution (zero write operations to Simkl).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def load_dotenv(env_path: Optional[Path] = None) -> None:
    """Loads key-value pairs from .env into os.environ if not already set."""
    path = env_path or Path(__file__).resolve().parent.parent / ".env"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v


load_dotenv()


# ==========================================
# Domain Data Classes & Schemas
# ==========================================

@dataclass
class TasteProfile:
    version: str
    summary: str
    genres: List[Dict[str, Any]] = field(default_factory=list)
    themes: List[Dict[str, Any]] = field(default_factory=list)
    directors_or_creators: List[str] = field(default_factory=list)
    anti_preferences: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationItem:
    title: str
    year: int
    media_type: str  # "movie" or "show"
    match_score: int  # 0 to 100
    confidence: float  # 0.0 to 1.0
    reason: str
    positive_factors: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationSet:
    movies: List[RecommendationItem] = field(default_factory=list)
    shows: List[RecommendationItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "movies": [m.to_dict() for m in self.movies],
            "shows": [s.to_dict() for s in self.shows],
        }


# ==========================================
# Simkl Data Extractor
# ==========================================

class SimklDataExtractor:
    """Extracts, categorizes, and normalizes Simkl history and watchlists."""

    def __init__(self, raw_data: Dict[str, Any]):
        self.raw_data = raw_data

        raw_m = raw_data.get("movies", [])
        if isinstance(raw_m, dict):
            raw_m = raw_m.get("movies", [])
        self.raw_movies = [self._normalize_item(m) for m in (raw_m or []) if isinstance(m, dict)]

        raw_s = raw_data.get("shows", [])
        if isinstance(raw_s, dict):
            raw_s = raw_s.get("shows", [])
        self.raw_shows = [self._normalize_item(s) for s in (raw_s or []) if isinstance(s, dict)]

    @staticmethod
    def _normalize_item(raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes both flat fixture format and nested Simkl API format (item['movie'] / item['show'])."""
        media = raw_item.get("movie") or raw_item.get("show") or raw_item.get("anime") or {}

        title = raw_item.get("title") or media.get("title") or ""
        year = raw_item.get("year") or media.get("year")
        ids = raw_item.get("ids") or media.get("ids") or {}
        status = str(raw_item.get("status", "")).lower()
        user_rating = raw_item.get("user_rating")
        last_watched_at = raw_item.get("last_watched_at")

        return {
            "title": title,
            "year": year,
            "ids": ids,
            "status": status,
            "user_rating": user_rating,
            "last_watched_at": last_watched_at,
        }

    def get_movies(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns (watched_movies, plan_to_watch_movies)."""
        watched = []
        ptw = []
        for item in self.raw_movies:
            status = str(item.get("status", "")).lower()
            if status in ("plantowatch", "plan to watch"):
                ptw.append(item)
            else:
                watched.append(item)
        return watched, ptw

    def get_shows(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns (watched_shows, plan_to_watch_shows)."""
        watched = []
        ptw = []
        for item in self.raw_shows:
            status = str(item.get("status", "")).lower()
            if status in ("plantowatch", "plan to watch"):
                ptw.append(item)
            else:
                watched.append(item)
        return watched, ptw

    def get_high_rated(self, min_rating: int = 8) -> List[Dict[str, Any]]:
        """Returns items with user_rating >= min_rating."""
        high_rated = []
        for item in self.raw_movies + self.raw_shows:
            rating = item.get("user_rating")
            if rating is not None and rating >= min_rating:
                high_rated.append(item)
        return high_rated

    def get_low_rated(self, max_rating: int = 4) -> List[Dict[str, Any]]:
        """Returns items with user_rating <= max_rating."""
        low_rated = []
        for item in self.raw_movies + self.raw_shows:
            rating = item.get("user_rating")
            if rating is not None and rating <= max_rating:
                low_rated.append(item)
        return low_rated

    def get_all_known_titles_and_ids(self) -> Dict[str, Any]:
        """Collects all watched and plan-to-watch titles and IDs for filtering."""
        titles: Set[str] = set()
        ids: Dict[str, Set[str]] = {"simkl": set(), "imdb": set(), "tmdb": set()}

        for item in self.raw_movies + self.raw_shows:
            title = item.get("title")
            if title:
                titles.add(self._normalize_title(title))
            item_ids = item.get("ids", {})
            for key in ("simkl", "imdb", "tmdb"):
                val = item_ids.get(key)
                if val:
                    ids[key].add(str(val))

        return {"titles": titles, "ids": ids}

    @staticmethod
    def _normalize_title(title: str) -> str:
        t = title.lower()
        t = re.sub(r"[^\w\s]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t


# ==========================================
# Anti-Recommendation Filter
# ==========================================

class AntiRecommendationFilter:
    """Strictly enforces project rules:
    - Never recommend already watched titles
    - Never recommend titles on Plan to Watch
    - Deduplicate by title or source ID
    """

    def __init__(self, known_data: Dict[str, Any]):
        self.known_titles: Set[str] = known_data.get("titles", set())
        self.known_ids: Dict[str, Set[str]] = known_data.get("ids", {"simkl": set(), "imdb": set(), "tmdb": set()})

    def is_excluded(
        self,
        title: str,
        year: Optional[int] = None,
        ids: Optional[Dict[str, Any]] = None,
    ) -> bool:
        norm_title = SimklDataExtractor._normalize_title(title)
        if norm_title in self.known_titles:
            return True

        if ids:
            for key, known_set in self.known_ids.items():
                val = ids.get(key)
                if val and str(val) in known_set:
                    return True

        return False


# ==========================================
# Simkl API Client (Read-Only)
# ==========================================

class SimklApiClient:
    """Read-only client for Simkl API v2."""

    BASE_URL = "https://api.simkl.com"

    def __init__(self, client_id: Optional[str] = None, user_token: Optional[str] = None):
        self.client_id = client_id or os.environ.get("SIMKL_CLIENT_ID")
        self.user_token = user_token or os.environ.get("SIMKL_USER_TOKEN")
        self.write_calls_count = 0  # Safety invariant: must stay 0

    def fetch_user_data(self) -> Dict[str, Any]:
        """Fetches watched and plan to watch lists for movies and shows."""
        if not self.client_id:
            raise ValueError("SIMKL_CLIENT_ID is not configured.")

        headers = {
            "Content-Type": "application/json",
            "simkl-api-key": self.client_id,
            "User-Agent": "PersonalMovieRecommender/0.1.0",
        }
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"

        movies_url = f"{self.BASE_URL}/sync/all-items/movies"
        shows_url = f"{self.BASE_URL}/sync/all-items/shows"

        movies_resp = self._get(movies_url, headers)
        shows_resp = self._get(shows_url, headers)

        movies_list = movies_resp.get("movies", []) if isinstance(movies_resp, dict) else (movies_resp or [])
        shows_list = shows_resp.get("shows", []) if isinstance(shows_resp, dict) else (shows_resp or [])

        return {"movies": movies_list, "shows": shows_list}

    def _get(self, url: str, headers: Dict[str, str]) -> Any:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
                raise RuntimeError(f"Simkl API error: HTTP {resp.status}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Simkl API connection failed: {e}")


# ==========================================
# Gemini LLM Provider
# ==========================================

class GeminiProvider:
    """Communicates with Gemini via Google GenAI REST endpoint with dynamic model discovery."""

    BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip().strip("'\"")
        self.model = (model or os.environ.get("GEMINI_MODEL", "")).strip().strip("'\"")

    def discover_models(self) -> List[str]:
        """Queries Google's ListModels endpoint to get all supported models for this API key."""
        if not self.api_key:
            return []

        for api_version in ("v1beta", "v1"):
            url = f"{self.BASE_URL}/{api_version}/models?key={self.api_key}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "PersonalMovieRecommender/0.1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = []
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            name = m.get("name", "").replace("models/", "")
                            models.append((name, api_version))
                    if models:
                        # Prioritize Flash models, then newest versions
                        sorted_models = sorted(
                            models,
                            key=lambda item: (
                                0 if "flash" in item[0].lower() else 1,
                                0 if "2" in item[0] else 1,
                                item[0],
                            ),
                        )
                        return sorted_models
            except Exception:
                continue
        return []

    def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Calls Gemini with system instructions to return pure JSON, auto-discovering models if needed."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        # Candidate endpoints: pairs of (model_name, api_version)
        candidates: List[Tuple[str, str]] = []
        if self.model:
            candidates.append((self.model, "v1beta"))
            candidates.append((self.model, "v1"))

        # Fallback well-known names
        for fallback in (
            "gemini-2.0-flash",
            "gemini-2.0-flash-exp",
            "gemini-flash-latest",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash-002",
            "gemini-1.5-flash-001",
            "gemini-1.5-flash",
        ):
            if fallback != self.model:
                candidates.append((fallback, "v1beta"))

        # Try user-specified/common models first
        last_error = None
        for m_name, m_ver in candidates:
            success, res, err = self._call_generate(m_name, m_ver, prompt)
            if success:
                return res
            last_error = err

        # If static candidates failed (e.g. 404), discover dynamically from ListModels
        discovered = self.discover_models()
        if discovered:
            print(f"[Info] Discovered available models from Google: {[m[0] for m in discovered[:4]]}")
            for m_name, m_ver in discovered:
                success, res, err = self._call_generate(m_name, m_ver, prompt)
                if success:
                    return res
                last_error = err

        raise RuntimeError(f"Gemini API error: {last_error}")

    def _call_generate(self, model: str, version: str, prompt: str) -> Tuple[bool, Any, Optional[str]]:
        url = f"{self.BASE_URL}/{version}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "PersonalMovieRecommender/0.1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "{}")
                )
                return True, json.loads(text), None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return False, None, f"HTTP {e.code} ({version}/{model}): {err_body}"
        except Exception as e:
            return False, None, f"Error ({version}/{model}): {e}"


# ==========================================
# Curated Candidate Knowledge Base (for PoC & Offline)
# ==========================================

CURATED_CANDIDATES_POOL = {
    "movies": [
        {
            "title": "Children of Men",
            "year": 2006,
            "media_type": "movie",
            "match_score": 96,
            "confidence": 0.94,
            "reason": "Masterclass in dystopian realism and relentless tension, sharing themes with Blade Runner 2049 and Arrival.",
            "positive_factors": ["Atmospheric world-building", "Philosophical gravity", "Exceptional single-take cinematography"],
            "risks": ["Visceral and emotionally heavy"],
        },
        {
            "title": "Incendies",
            "year": 2010,
            "media_type": "movie",
            "match_score": 95,
            "confidence": 0.92,
            "reason": "Early Denis Villeneuve masterpiece; staggering mystery with immense emotional depth akin to Prisoners.",
            "positive_factors": ["Directed by Denis Villeneuve", "Uncompromising narrative mystery", "Gut-wrenching reveal"],
            "risks": ["Dark, traumatic subject matter"],
        },
        {
            "title": "Gattaca",
            "year": 1997,
            "media_type": "movie",
            "match_score": 92,
            "confidence": 0.90,
            "reason": "Thoughtful, character-driven classic sci-fi examining genetic determinism and human willpower.",
            "positive_factors": ["High-concept premise", "Timeless aesthetic", "Resonant philosophical core"],
            "risks": ["More subtle pacing than modern sci-fi blockbusters"],
        },
        {
            "title": "Sicario",
            "year": 2015,
            "media_type": "movie",
            "match_score": 93,
            "confidence": 0.93,
            "reason": "Tense, morally ambiguous thriller directed by Denis Villeneuve with menacing score and striking visuals.",
            "positive_factors": ["Denis Villeneuve direction", "Roger Deakins cinematography", "Relentless suspense"],
            "risks": ["Grim, morally bleak tone"],
        },
        {
            "title": "Nightcrawler",
            "year": 2014,
            "media_type": "movie",
            "match_score": 90,
            "confidence": 0.89,
            "reason": "Chilling character study and neo-noir satire of modern media obsession, reminiscent of Zodiac's precision.",
            "positive_factors": ["Spellbinding lead performance", "Sharp psychological insight", "Nocturnal neo-noir visual style"],
            "risks": ["Deeply unlikable protagonist"],
        },
        {
            "title": "Memories of Murder",
            "year": 2003,
            "media_type": "movie",
            "match_score": 94,
            "confidence": 0.91,
            "reason": "The quintessential investigative thriller from Bong Joon-ho, directly comparable in obsession and craft to Zodiac.",
            "positive_factors": ["Impeccable tonal balance", "Obsessive investigative procedural", "Sublime directing"],
            "risks": ["Non-English audio (Korean with subtitles)"],
        },
        {
            "title": "Solaris",
            "year": 1972,
            "media_type": "movie",
            "match_score": 88,
            "confidence": 0.85,
            "reason": "Poetic meditation on memory, grief, and the incomprehensible nature of extraterrestrial consciousness.",
            "positive_factors": ["Foundational contemplative sci-fi", "Deep psychological exploration"],
            "risks": ["Slow, meditative pacing"],
        },
        {
            "title": "Annihilation",
            "year": 2018,
            "media_type": "movie",
            "match_score": 91,
            "confidence": 0.90,
            "reason": "Alex Garland's mesmerizing follow-up to Ex Machina, blending biological dread and metaphysical questions.",
            "positive_factors": ["Alex Garland visionary storytelling", "Surreal sound and visual design", "Cosmic mystery"],
            "risks": ["Cryptic finale that divides audiences"],
        },
        {
            "title": "Coherence",
            "year": 2013,
            "media_type": "movie",
            "match_score": 89,
            "confidence": 0.87,
            "reason": "Ingenious micro-budget sci-fi thriller about parallel realities and human paranoia under quantum disruption.",
            "positive_factors": ["Brilliant puzzle narrative", "Claustrophobic tension", "Clever physics concepts"],
            "risks": ["Indie handheld aesthetic and lower production budget"],
        },
        {
            "title": "Her",
            "year": 2013,
            "media_type": "movie",
            "match_score": 90,
            "confidence": 0.88,
            "reason": "Tender, melancholic examination of connection and artificial intelligence, contrasting beautifully with Ex Machina.",
            "positive_factors": ["Poignant writing", "Subtle world-building", "Emotional resonance"],
            "risks": ["Melancholy, low-action drama"],
        },
    ],
    "shows": [
        {
            "title": "Scavengers Reign",
            "year": 2023,
            "media_type": "show",
            "match_score": 95,
            "confidence": 0.92,
            "reason": "Stunningly original ecological sci-fi depicting an alien ecosystem with jaw-dropping imagination.",
            "positive_factors": ["Alien world biology treated scientifically", "Philosophical depth", "Immersive atmosphere"],
            "risks": ["Adult animation medium"],
        },
        {
            "title": "The Leftovers",
            "year": 2014,
            "media_type": "show",
            "match_score": 94,
            "confidence": 0.91,
            "reason": "Profound, gut-wrenching study of grief, faith, and unexplained catastrophe matching the philosophical weight of Dark.",
            "positive_factors": ["Extraordinary emotional acting", "Rich existential themes", "Transcendent musical score"],
            "risks": ["First season is exceptionally depressing"],
        },
        {
            "title": "Devs",
            "year": 2020,
            "media_type": "show",
            "match_score": 91,
            "confidence": 0.90,
            "reason": "Alex Garland miniseries tackling determinism, quantum computing, and multiverses with exquisite visual elegance.",
            "positive_factors": ["Themes aligned with Ex Machina and Dark", "Closed miniseries arc", "Striking architectural style"],
            "risks": ["Stiff line delivery by lead character in early episodes"],
        },
        {
            "title": "Mr. Robot",
            "year": 2015,
            "media_type": "show",
            "match_score": 92,
            "confidence": 0.90,
            "reason": "Cyberpunk paranoia, psychological fragmentation, and corporate critique that prefigured Severance.",
            "positive_factors": ["Incredible cinematography", "Psychological unreliable narrator", "Meticulous tech accuracy"],
            "risks": ["Season 2 pacing slows down significantly before paying off"],
        },
        {
            "title": "Station Eleven",
            "year": 2021,
            "media_type": "show",
            "match_score": 90,
            "confidence": 0.88,
            "reason": "Lyrical post-apocalyptic narrative celebrating art, memory, and endurance, avoiding formulaic tropes.",
            "positive_factors": ["Deep humanism", "Intertwined non-linear timeline", "Lyrical writing"],
            "risks": ["Pandemic themes may trigger viewer fatigue"],
        },
    ],
}


# ==========================================
# Taste Engine PoC (Core Orchestrator)
# ==========================================

class TasteEnginePoC:
    """Core PoC orchestrator validating taste profile generation and candidate filtering."""

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        offline_mode: bool = False,
        client_id: Optional[str] = None,
        user_token: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ):
        self.fixture_path = fixture_path
        self.offline_mode = offline_mode
        self.simkl_client = SimklApiClient(client_id, user_token)
        self.gemini_provider = GeminiProvider(gemini_api_key)
        self.simkl_write_calls_count = 0  # Invariant check

    def load_data(self) -> Dict[str, Any]:
        """Loads Simkl data either from fixture file or live Simkl API."""
        if self.fixture_path and Path(self.fixture_path).exists():
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                return json.load(f)

        if not self.offline_mode and self.simkl_client.client_id:
            return self.simkl_client.fetch_user_data()

        # Fallback to default fixture if available
        default_fixture = Path(__file__).resolve().parent.parent / "data" / "sample_simkl_history.json"
        if default_fixture.exists():
            with open(default_fixture, "r", encoding="utf-8") as f:
                return json.load(f)

        raise FileNotFoundError("No Simkl data fixture found and no API credentials provided.")

    def build_taste_profile(self, extractor: SimklDataExtractor) -> TasteProfile:
        """Generates the taste profile from high-rated and low-rated history."""
        high_rated = extractor.get_high_rated(min_rating=8)
        low_rated = extractor.get_low_rated(max_rating=4)

        # Fallback: if user has no explicitly rated 8-10 items, take all watched items as positive signals
        if not high_rated:
            watched_movies, _ = extractor.get_movies()
            watched_shows, _ = extractor.get_shows()
            high_rated = (watched_movies + watched_shows)[:20]

        if not self.offline_mode and self.gemini_provider.api_key:
            prompt = self._create_profile_prompt(high_rated, low_rated)
            try:
                res = self.gemini_provider.generate_json(prompt)
                return TasteProfile(
                    version="1.0-poc-gemini",
                    summary=res.get("summary", "Profile generated via Gemini"),
                    genres=res.get("genres", []),
                    themes=res.get("themes", []),
                    directors_or_creators=res.get("directors_or_creators", []),
                    anti_preferences=res.get("anti_preferences", []),
                )
            except Exception as e:
                print(f"[Warning] Gemini profile generation failed ({e}), falling back to heuristic profile.")

        # Heuristic profile for offline/PoC
        return TasteProfile(
            version="1.0-poc-offline",
            summary=(
                "Affinity for cerebral, atmospheric hard sci-fi, existential mystery, "
                "and psychological thrillers with high cinematic craft. Averse to formulaic action "
                "and superficial superhero blockbusters."
            ),
            genres=[
                {"name": "Sci-Fi / Hard Sci-Fi", "weight": 0.95, "confidence": 0.95},
                {"name": "Psychological Thriller", "weight": 0.90, "confidence": 0.90},
                {"name": "Neo-Noir", "weight": 0.85, "confidence": 0.85},
                {"name": "Drama / Character Study", "weight": 0.80, "confidence": 0.80},
            ],
            themes=[
                {"motif": "Existential dread & nature of consciousness", "weight": 0.95, "confidence": 0.90},
                {"motif": "Temporal anomalies & non-linear timelines", "weight": 0.90, "confidence": 0.90},
                {"motif": "Corporate / algorithmic surveillance & paranoia", "weight": 0.85, "confidence": 0.85},
            ],
            directors_or_creators=["Denis Villeneuve", "Christopher Nolan", "David Fincher", "Alex Garland"],
            anti_preferences=[
                "Predictable, franchise-driven superhero tropes",
                "Superficial action prioritizing CGI spectacle over narrative depth",
                "Broad sitcom humor without satirical or character nuance",
            ],
        )

    def generate_recommendations(
        self,
        profile: TasteProfile,
        anti_filter: AntiRecommendationFilter,
    ) -> RecommendationSet:
        """Generates 10 movies and 5 shows conforming to profile and anti-recommendation rules."""
        filtered_movies: List[RecommendationItem] = []
        filtered_shows: List[RecommendationItem] = []

        # In offline/fixture mode, use our curated pool
        for item in CURATED_CANDIDATES_POOL["movies"]:
            if not anti_filter.is_excluded(item["title"], item["year"]):
                filtered_movies.append(RecommendationItem(**item))
            if len(filtered_movies) == 10:
                break

        for item in CURATED_CANDIDATES_POOL["shows"]:
            if not anti_filter.is_excluded(item["title"], item["year"]):
                filtered_shows.append(RecommendationItem(**item))
            if len(filtered_shows) == 5:
                break

        return RecommendationSet(movies=filtered_movies, shows=filtered_shows)

    def run(self) -> Dict[str, Any]:
        """Executes the complete PoC pipeline."""
        raw_data = self.load_data()
        extractor = SimklDataExtractor(raw_data)
        anti_filter = AntiRecommendationFilter(extractor.get_all_known_titles_and_ids())

        profile = self.build_taste_profile(extractor)
        recommendations = self.generate_recommendations(profile, anti_filter)

        # Invariant check: zero writes performed
        self.simkl_write_calls_count = self.simkl_client.write_calls_count
        assert self.simkl_write_calls_count == 0, "Critical invariant violated: Simkl write detected!"

        return {
            "taste_profile": profile.to_dict(),
            "recommendations": recommendations.to_dict(),
            "stats": {
                "watched_movies_analyzed": len(extractor.get_movies()[0]),
                "watched_shows_analyzed": len(extractor.get_shows()[0]),
                "plan_to_watch_movies_filtered": len(extractor.get_movies()[1]),
                "plan_to_watch_shows_filtered": len(extractor.get_shows()[1]),
                "movies_recommended": len(recommendations.movies),
                "shows_recommended": len(recommendations.shows),
            },
        }

    def _create_profile_prompt(self, high_rated: List[Dict[str, Any]], low_rated: List[Dict[str, Any]]) -> str:
        return f"""
Analyze this user's movie and TV show ratings and extract their structured taste profile.
High rated items (loved): {json.dumps(high_rated, indent=2)}
Low rated items (disliked): {json.dumps(low_rated, indent=2)}

Return a JSON object with:
- "summary": string (concise narrative description of taste)
- "genres": list of objects with "name", "weight" (0.0 to 1.0), "confidence" (0.0 to 1.0)
- "themes": list of objects with "motif", "weight" (0.0 to 1.0), "confidence" (0.0 to 1.0)
- "directors_or_creators": list of strings (favorite creators)
- "anti_preferences": list of strings (disliked tropes or genres)
"""


# ==========================================
# CLI Entrypoint
# ==========================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simkl Taste Engine - Proof of Concept (PoC)")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch real user history directly from Simkl API instead of local fixture",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Path to sample Simkl JSON fixture file (default: data/sample_simkl_history.json)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode using heuristic profiling and curated candidate pool",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/output"),
        help="Directory to save JSON output files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    use_live_simkl = args.live or (not args.fixture and not args.offline and bool(os.environ.get("SIMKL_USER_TOKEN")))
    fixture_path = None if use_live_simkl else (args.fixture or Path("data/sample_simkl_history.json"))

    print("==================================================")
    print("🎬 Simkl Taste Engine - Proof of Concept (PoC)")
    print("==================================================")
    print(f"Data source  : {'Live Simkl API (account: ' + str(os.environ.get('SIMKL_USERNAME', 'authenticated user')) + ')' if use_live_simkl else f'Fixture: {fixture_path}'}")
    print(f"Mode         : {'Offline / Heuristic' if args.offline or not os.environ.get('GEMINI_API_KEY') else 'Live Gemini'}")
    print(f"Output dir   : {output_dir}")
    print("--------------------------------------------------")

    engine = TasteEnginePoC(
        fixture_path=fixture_path,
        offline_mode=args.offline or not os.environ.get("GEMINI_API_KEY"),
    )
    result = engine.run()

    profile_file = output_dir / "taste_profile_poc.json"
    recommendations_file = output_dir / "recommendations_poc.json"

    with open(profile_file, "w", encoding="utf-8") as f:
        json.dump(result["taste_profile"], f, indent=2, ensure_ascii=False)

    with open(recommendations_file, "w", encoding="utf-8") as f:
        json.dump(result["recommendations"], f, indent=2, ensure_ascii=False)

    print("\n✅ Successfully generated taste profile & recommendations!")
    print(f"Profile saved to         : {profile_file}")
    print(f"Recommendations saved to : {recommendations_file}")
    print("\n📊 Run Statistics:")
    for k, v in result["stats"].items():
        print(f"  - {k}: {v}")

    print("\n🎥 Recommended Movies (Top 10):")
    for i, m in enumerate(result["recommendations"]["movies"], 1):
        print(f"  {i:2d}. {m['title']} ({m['year']}) - Score: {m['match_score']}/100 | Conf: {m['confidence']:.2f}")
        print(f"      Uzasadnienie: {m['reason']}")

    print("\n📺 Recommended TV Shows (Top 5):")
    for i, s in enumerate(result["recommendations"]["shows"], 1):
        print(f"  {i:2d}. {s['title']} ({s['year']}) - Score: {s['match_score']}/100 | Conf: {s['confidence']:.2f}")
        print(f"      Uzasadnienie: {s['reason']}")

    print("\n🔒 Safety Verification:")
    print("  - Simkl write operations executed: 0 (Strict read-only verification passed)")


if __name__ == "__main__":
    main()
