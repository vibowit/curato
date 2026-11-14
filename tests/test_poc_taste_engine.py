"""Tests for the PoC Taste Engine (scripts/poc_taste_engine.py).

Validates:
1. Simkl data loading and normalization.
2. Strict anti-recommendation filtering (excluding watched & plan to watch items).
3. Schema conformity for taste profile (weights, confidence, anti-preferences).
4. Schema conformity for recommendations (10 movies, 5 shows, factors, risks, scores).
5. Absolute guarantee against automatic write operations to Simkl.
"""

import json

# Add project root to path
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.poc_taste_engine import (  # noqa: E402
    AntiRecommendationFilter,
    RecommendationItem,
    RecommendationSet,
    SimklDataExtractor,
    TasteEnginePoC,
    TasteProfile,
)


class TestPocTasteEngine(unittest.TestCase):
    def setUp(self):
        self.fixture_path = PROJECT_ROOT / "data" / "sample_simkl_history.json"
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self.fixture_data = json.load(f)
        self.extractor = SimklDataExtractor(self.fixture_data)

    def test_simkl_data_extraction(self):
        """Test extraction and categorization of watched and plan to watch items."""
        watched_movies, ptw_movies = self.extractor.get_movies()
        watched_shows, ptw_shows = self.extractor.get_shows()

        self.assertGreaterEqual(len(watched_movies), 5)
        self.assertGreaterEqual(len(ptw_movies), 2)
        self.assertGreaterEqual(len(watched_shows), 4)
        self.assertGreaterEqual(len(ptw_shows), 1)

        # Verify high ratings and low ratings separation
        high_rated = self.extractor.get_high_rated(min_rating=8)
        low_rated = self.extractor.get_low_rated(max_rating=4)

        high_titles = [item["title"] for item in high_rated]
        low_titles = [item["title"] for item in low_rated]

        self.assertIn("Blade Runner 2049", high_titles)
        self.assertIn("Dark", high_titles)
        self.assertIn("Fast X", low_titles)
        self.assertIn("Madame Web", low_titles)

    def test_simkl_nested_api_format_extraction(self):
        """Test extraction when Simkl API returns nested objects under 'movie' or 'show'."""
        nested_data = {
            "movies": [
                {
                    "status": "completed",
                    "user_rating": 9,
                    "last_watched_at": "2024-01-01T00:00:00Z",
                    "movie": {
                        "title": "Inception",
                        "year": 2010,
                        "ids": {"simkl": 1234, "imdb": "tt1375666", "tmdb": "27205"},
                    },
                },
                {
                    "status": "plantowatch",
                    "user_rating": None,
                    "movie": {
                        "title": "Oppenheimer",
                        "year": 2023,
                        "ids": {"simkl": 5678, "imdb": "tt15398776", "tmdb": "872585"},
                    },
                },
            ],
            "shows": [
                {
                    "status": "completed",
                    "user_rating": 10,
                    "show": {
                        "title": "Breaking Bad",
                        "year": 2008,
                        "ids": {"simkl": 9999, "imdb": "tt0903747", "tmdb": "1396"},
                    },
                }
            ],
        }

        extractor = SimklDataExtractor(nested_data)
        watched_m, ptw_m = extractor.get_movies()
        watched_s, ptw_s = extractor.get_shows()

        self.assertEqual(len(watched_m), 1)
        self.assertEqual(watched_m[0]["title"], "Inception")
        self.assertEqual(watched_m[0]["year"], 2010)
        self.assertEqual(len(ptw_m), 1)
        self.assertEqual(ptw_m[0]["title"], "Oppenheimer")
        self.assertEqual(len(watched_s), 1)
        self.assertEqual(watched_s[0]["title"], "Breaking Bad")

        high_rated = extractor.get_high_rated(min_rating=8)
        self.assertEqual(len(high_rated), 2)
        titles = [item["title"] for item in high_rated]
        self.assertIn("Inception", titles)
        self.assertIn("Breaking Bad", titles)

    def test_anti_recommendation_filter(self):
        """Test that watched and plan-to-watch items are strictly rejected."""
        anti_filter = AntiRecommendationFilter(self.extractor.get_all_known_titles_and_ids())

        # Should be rejected: watched
        self.assertTrue(anti_filter.is_excluded("Blade Runner 2049", 2017, {"simkl": 546252}))
        self.assertTrue(anti_filter.is_excluded("Arrival", 2016))
        self.assertTrue(anti_filter.is_excluded("dark", 2017))  # Case-insensitive

        # Should be rejected: plan to watch
        self.assertTrue(anti_filter.is_excluded("Alien: Romulus", 2024))
        self.assertTrue(anti_filter.is_excluded("Fallout", 2024))
        self.assertTrue(anti_filter.is_excluded("Poor Things", 2023))

        # Should be allowed: new unwatched movies/shows
        self.assertFalse(anti_filter.is_excluded("Children of Men", 2006))
        self.assertFalse(anti_filter.is_excluded("Scavengers Reign", 2023))

    def test_taste_profile_validation(self):
        """Test TasteProfile dataclass/schema validation."""
        profile = TasteProfile(
            version="1.0-poc",
            summary="Fan of contemplative, high-concept sci-fi and tense psychological thrillers.",
            genres=[
                {"name": "Sci-Fi", "weight": 0.95, "confidence": 0.9},
                {"name": "Psychological Thriller", "weight": 0.9, "confidence": 0.85},
            ],
            themes=[
                {"motif": "Existential dread / Identity", "weight": 0.9, "confidence": 0.85},
                {
                    "motif": "Time anomalies & non-linear storytelling",
                    "weight": 0.95,
                    "confidence": 0.9,
                },
            ],
            directors_or_creators=["Denis Villeneuve", "Christopher Nolan", "David Fincher"],
            anti_preferences=[
                "Formulaic superhero blockbusters",
                "Superficial action without character depth",
            ],
        )

        profile_dict = profile.to_dict()
        self.assertEqual(profile_dict["version"], "1.0-poc")
        self.assertEqual(len(profile_dict["genres"]), 2)
        self.assertIn("Denis Villeneuve", profile_dict["directors_or_creators"])
        self.assertIn("Formulaic superhero blockbusters", profile_dict["anti_preferences"])

    def test_recommendation_set_validation(self):
        """Test that recommendation sets validate exact quantities and schemas."""
        movies = [
            RecommendationItem(
                title=f"Movie {i}",
                year=2010 + i,
                media_type="movie",
                match_score=85 + i,
                confidence=0.88,
                reason="Atmospheric storytelling with deep psychological themes.",
                positive_factors=["Strong direction", "Philosophical depth"],
                risks=["Slow burn pacing"],
            )
            for i in range(10)
        ]

        shows = [
            RecommendationItem(
                title=f"Show {i}",
                year=2015 + i,
                media_type="show",
                match_score=90 + i,
                confidence=0.9,
                reason="Complex narrative mystery with high production value.",
                positive_factors=["Mind-bending mystery", "Tight writing"],
                risks=["Requires patient viewing"],
            )
            for i in range(5)
        ]

        rec_set = RecommendationSet(movies=movies, shows=shows)
        self.assertEqual(len(rec_set.movies), 10)
        self.assertEqual(len(rec_set.shows), 5)

        # Check serialization
        data = rec_set.to_dict()
        self.assertEqual(len(data["movies"]), 10)
        self.assertEqual(len(data["shows"]), 5)
        self.assertEqual(data["movies"][0]["media_type"], "movie")
        self.assertEqual(data["shows"][0]["media_type"], "show")

    def test_engine_offline_execution_and_no_simkl_write(self):
        """Test end-to-end execution in mock/offline mode with guarantee of zero Simkl writes."""
        engine = TasteEnginePoC(fixture_path=self.fixture_path, offline_mode=True)
        result = engine.run()

        profile = result["taste_profile"]
        recommendations = result["recommendations"]

        # Verify profile
        self.assertTrue(len(profile["genres"]) > 0)
        self.assertTrue(len(profile["anti_preferences"]) > 0)

        # Verify recommendations count: 10 movies, 5 shows
        self.assertEqual(len(recommendations["movies"]), 10)
        self.assertEqual(len(recommendations["shows"]), 5)

        # Verify all recommendations passed anti-recommendation filter
        known_titles = {
            t["title"].lower()
            for t in self.extractor.get_movies()[0]
            + self.extractor.get_movies()[1]
            + self.extractor.get_shows()[0]
            + self.extractor.get_shows()[1]
        }
        for movie in recommendations["movies"]:
            self.assertNotIn(movie["title"].lower(), known_titles)
            self.assertEqual(movie["media_type"], "movie")
            self.assertTrue(0 <= movie["match_score"] <= 100)
            self.assertTrue(0.0 <= movie["confidence"] <= 1.0)

        for show in recommendations["shows"]:
            self.assertNotIn(show["title"].lower(), known_titles)
            self.assertEqual(show["media_type"], "show")
            self.assertTrue(0 <= show["match_score"] <= 100)
            self.assertTrue(0.0 <= show["confidence"] <= 1.0)

        # Guarantee zero POST/PUT/DELETE requests were made
        self.assertEqual(engine.simkl_write_calls_count, 0)


if __name__ == "__main__":
    unittest.main()
