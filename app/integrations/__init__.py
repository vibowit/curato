"""Integrations package for external services (Simkl, TMDB, LLM)."""

from app.integrations.simkl import SimklClient
from app.integrations.tmdb import TMDBClient

__all__ = ["SimklClient", "TMDBClient"]
