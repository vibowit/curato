#!/usr/bin/env python3
"""Manual verification script for Phase 3: Recommendation Engine.

Executes:
1. Check or perform Simkl synchronization (Phase 1).
2. Check or generate active Taste Profile (Phase 2).
3. Execute Recommendation Run (Phase 3).
4. Print formatted recommendations and verify DoD criteria.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.history import WatchHistory
from app.models.recommendation import RecommendationRun
from app.models.taste import TasteProfile
from app.schemas.recommendation import RecommendationRunCreateRequest
from app.services.recommendations import RecommendationService
from app.services.sync import SyncService
from app.services.taste import TasteService


async def main():
    print("=" * 65)
    print("🎬 MANUALNA WERYFIKACJA FAZY 3: SILNIK REKOMENDACJI")
    print("=" * 65)

    db = SessionLocal()
    try:
        # Krok 1: Weryfikacja historii Simkl
        history_count = db.query(WatchHistory).count()
        print("\n[1/3] Sprawdzanie historii Simkl w lokalnej bazie SQLite...")
        if history_count == 0:
            print("      Brak historii w bazie. Uruchamiam synchronizację z API Simkl...")
            sync_service = SyncService(db_session=db)
            sync_result = await sync_service.sync_simkl()
            print(
                f"      ✅ Zsynchronizowano: {sync_result.total_synced} pozycji "
                f"(status: {sync_result.status})"
            )
        else:
            print(f"      ✅ W bazie znajduje się {history_count} pozycji z historii Simkl.")

        # Krok 2: Weryfikacja aktywnego profilu gustu
        print("\n[2/3] Sprawdzanie aktywnego profilu gustu (Taste Profile)...")
        active_profile = db.query(TasteProfile).filter(TasteProfile.active.is_(True)).first()
        if not active_profile:
            print("      Brak aktywnego profilu. Generuję profil gustu przez LLM (Gemini)...")
            taste_service = TasteService()
            profile_model = await taste_service.generate_profile(db)
            print(f"      ✅ Wygenerowano aktywny profil: wersja {profile_model.version}")
        else:
            print(f"      ✅ Aktywny profil gustu: wersja {active_profile.version}")

        # Krok 3: Generowanie rekomendacji (Faza 3)
        print("\n[3/3] Uruchamianie silnika rekomendacji (TMDB + Filtry + Ranking + LLM)...")
        rec_service = RecommendationService()
        req = RecommendationRunCreateRequest(
            movie_limit=10,
            show_limit=5,
            mode="weekly",
        )
        run: RecommendationRun = await rec_service.create_recommendation_run(db, req)
        read_schema = rec_service.to_read_schema(run)

        print("\n" + "=" * 65)
        print(f"✅ PRZEBIEG #{read_schema.id} ZAKOŃCZONY POMYŚLNIE (Status: {read_schema.status})")
        print(f"   Model: {read_schema.model_provider} ({read_schema.model_name})")
        print(f"   Profil: {read_schema.profile_version}")
        print(f"   Podsumowanie: {read_schema.summary}")
        print("=" * 65)

        movies = [
            r
            for r in read_schema.recommendations
            if r.media_item and r.media_item.media_type == "movie"
        ]
        shows = [
            r
            for r in read_schema.recommendations
            if r.media_item and r.media_item.media_type == "show"
        ]

        print(f"\n🎥 REKOMENDOWANE FILMY ({len(movies)} z 10):")
        for i, m in enumerate(movies, 1):
            item = m.media_item
            print(f"  {i:2d}. {item.title} ({item.year or 'N/A'}) [TMDB ID: {item.tmdb_id}]")
            print(
                f"      Score: {m.match_score:.1f}/100 | "
                f"Pewność: {m.confidence:.2f} | Status: {m.status}"
            )
            print(f"      Uzasadnienie: {m.reason}")
            if m.positive_factors:
                print(f"      Zalety: {', '.join(m.positive_factors)}")
            if m.risks:
                print(f"      Ryzyka: {', '.join(m.risks)}")

        print(f"\n📺 REKOMENDOWANE SERIALE ({len(shows)} z 5):")
        for i, s in enumerate(shows, 1):
            item = s.media_item
            print(f"  {i:2d}. {item.title} ({item.year or 'N/A'}) [TMDB ID: {item.tmdb_id}]")
            print(
                f"      Score: {s.match_score:.1f}/100 | "
                f"Pewność: {s.confidence:.2f} | Status: {s.status}"
            )
            print(f"      Uzasadnienie: {s.reason}")
            if s.positive_factors:
                print(f"      Zalety: {', '.join(s.positive_factors)}")
            if s.risks:
                print(f"      Ryzyka: {', '.join(s.risks)}")

        has_all_tmdb_ids = all(
            r.media_item and r.media_item.tmdb_id for r in read_schema.recommendations
        )
        all_pending = all(r.status == "pending" for r in read_schema.recommendations)

        print("\n" + "=" * 65)
        print("KRYTERIA AKCEPTACJI FAZY 3:")
        print(f"  - Liczba filmów: {len(movies)} / 10 -> {'OK' if len(movies) == 10 else 'UWAGA'}")
        print(f"  - Liczba seriali: {len(shows)} / 5 -> {'OK' if len(shows) == 5 else 'UWAGA'}")
        print(f"  - Identyfikatory TMDB: {'OK' if has_all_tmdb_ids else 'BRAK'}")
        print(f"  - Status 'pending' (brak zapisu w Simkl): {'OK' if all_pending else 'BŁĄD'}")
        print("=" * 65)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
