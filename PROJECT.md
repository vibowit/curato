---
id: "movie-recommend"
title: "System Rekomendacji Filmów i Seriali (Simkl + Gemini/OpenAI + FastAPI + MCP)"
status: in_progress
priority: P1
category: dev
created: "2026-11-06"
updated: "2026-11-14"
next_action: "Przeprowadzić weryfikację integracji MCP na żywo w Antigravity/ChatGPT oraz zaplanować funkcje po-MVP (powiadomienia Pushover, analiza zmian gustu)"
tags:
  - movie-recommendation
  - simkl
  - fastapi
  - sqlite
  - mcp
  - gemini
  - uv
---

# System Rekomendacji Filmów i Seriali

Prywatny system rekomendacji filmów i seriali oparty na Simkl, profilu gustu użytkownika oraz analizie LLM (Gemini/OpenAI), z dostępem przez FastAPI i MCP dla klientów Antigravity oraz ChatGPT.

## Cel i Pożądany Rezultat (Definition of Done)

Jasno zdefiniowany cel końcowy projektu (MVP):
- [x] Działający skrypt PoC (Simkl Taste Engine) walidujący jakość profilowania i rekomendacji LLM.
- [x] Stabilny szkielet aplikacji w `FastAPI` z bazą `SQLite` i migracjami.
- [x] Integracja z Simkl: autoryzacja, synchronizacja biblioteki/ocen/Plan to Watch, idempotentny zapis wyłącznie zaakceptowanych pozycji.
- [x] Wersjonowany profil gustu użytkownika z możliwością ręcznej korekty.
- [x] Silnik rekomendacji integrujący TMDB i LLM (10 filmów, 5 seriali na edycję) z uzasadnieniami i bez duplikatów.
- [x] Prosty interfejs użytkownika do przeglądu i zatwierdzania/odrzucania propozycji.
- [x] Serwer MCP (STDIO dla Antigravity, HTTPS dla ChatGPT) udostępniający te same serwisy domenowe.
- [x] Testy automatyczne (pokrycie kluczowych modułów > 80%, testy mockujące Simkl/TMDB/LLM).
- [x] Dokumentacja uruchomieniowa i szablon `.env.example`.

## Bieżący Stan i Architektura

- **Stos technologiczny**:
  - Język i środowisko: Python 3.11+, zarządzanie pakietami przez `uv` (`pyproject.toml`)
  - Narzędzia jakości kodu: `ruff` (linter/formatter), `pytest` (testy)
  - Backend: `FastAPI`, `Pydantic v2`
  - Baza danych: `SQLite` (lokalny plik, daty w UTC)
  - Integracje zewnętrzne: Simkl API, TMDB API, Google GenAI SDK (Gemini) / OpenAI API
  - Interfejs agentowy: MCP server (STDIO / Streamable HTTP)
- **Stan bieżący**:
  - Dokumentacja projektowa i architektoniczna zweryfikowana (`PRODUCT.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `API_CONTRACTS.md`, `RECOMMENDATION_ENGINE.md`, `AGENTS.md`, `ROADMAP.md`).
  - Zainicjowano repozytorium Git oraz skonfigurowano środowisko (`pyproject.toml`, `.env.example`, `.gitignore`).
  - Zaimplementowano i przetestowano skrypt badawczy `scripts/poc_taste_engine.py` (ekstrakcja historii Simkl, filtr anty-rekomendacji, integracja z Simkl API przez OAuth 2.0 Device Flow oraz profilowanie przez model Gemini 2.5 Flash).
  - Skrypt pomyślnie wygenerował pliki `data/output/taste_profile_poc.json` i `data/output/recommendations_poc.json`.
  - Użytkownik przeprowadził ewaluację jakościową: profil gustu został oceniony jako **bardzo trafny**. Zgłoszono uwagę dotyczącą preferencji ograniczenia animacji i zbalansowania sci-fi w docelowej integracji z TMDB (Etap 3).
  - Zrealizowano i przetestowano **Etap 0 (Fundament)**:
    - Utworzono strukturę modułów w `app/` (`core`, `models`, `schemas`, `api`, `services`, `integrations`).
    - Skonfigurowano walidację ustawień z `pydantic-settings` i bezpieczne maskowanie sekretów (`SecretStr`).
    - Zaimplementowano deklaratywne modele bazy danych SQLite w `SQLAlchemy 2.0` wg `DATA_MODEL.md` (`media_items`, `watch_history`, `taste_profiles`, `recommendation_runs`, `recommendations`, `user_decisions`, `sync_state`, `app_settings`).
    - Skonfigurowano migracje bazy danych w `Alembic` oraz wygenerowano i zweryfikowano pierwszą migrację `b00467105c7b_initial_schema.py`.
    - Zaimplementowano fabrykę aplikacji `FastAPI`, middleware korelacji `X-Request-ID`, ustandaryzowaną obsługę błędów wg `API_CONTRACTS.md` oraz endpoint `GET /api/health`.
    - Przygotowano zestaw testów automatycznych w `pytest` (16 testów przechodzi w 100%) oraz czystą weryfikację `ruff`.
  - Zrealizowano i przetestowano **Etap 1 (Simkl)**:
    - Zaimplementowano asynchronicznego klienta Simkl API (`app/integrations/simkl.py`) z nagłówkami autoryzacji (`simkl-api-key`, `Authorization: Bearer`), obsługą limitów (10 GET/s, 1 POST/s), retry z backoffem oraz ścisłym śledzeniem liczby operacji zapisu (`write_calls_count`).
    - Zaimplementowano serwis synchronizacji (`app/services/sync.py`) z obsługą pełnej i przyrostowej synchronizacji (`sync_state.last_success_at`), deduplikacją i upsertem do tabel `media_items` i `watch_history`.
    - Zaimplementowano serwis kontrolowanego zapisu (`app/services/watchlist.py`), gwarantujący nienegocjowalną zasadę: zapis do Simkl (`plantowatch`) wymaga uprzedniej, jawnej akceptacji użytkownika (`status == 'accepted'`), a wielokrotne wywołania są w pełni idempotentne.
    - Zaimplementowano endpointy REST API (`app/api/v1/sync.py`): `POST /api/sync/simkl` oraz `GET /api/sync/simkl/status`.
    - Rozszerzono zestaw testów automatycznych do 32 testów (`pytest`) z pokryciem 100% dla klienta Simkl, serwisu synchronizacji, idempotencji zapisu oraz endpointów API.
  - Zrealizowano i przetestowano **Etap 2 (Profil gustu)**:
    - Zaimplementowano rygorystyczne schematy domenowe Pydantic (`app/schemas/taste.py`): rozdzielenie wag cech (`weight`) od pewności modelu (`confidence`), rozdzielenie preferencji stałych od chwilowych (`temporary_interests`), ustrukturyzowane motywy, reżyserzy/twórcy oraz antypreferencje.
    - Zaimplementowano moduł integracyjny LLM (`app/integrations/llm/`): protokół `LLMProvider` oraz asynchronicznego klienta `GeminiLLMClient` z walidacją JSON, automatycznym fallbackiem modeli (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`) oraz mapowaniem błędów (`AuthRequiredException`, `RateLimitedException`, `UpstreamErrorException`).
    - Zaimplementowano domenowy serwis `TasteService` (`app/services/taste.py`): ekstrakcja historii z bazy SQLite (`watch_history` + `media_items`), kalkulacja proweniencji (`based_on_sync_at`), promptowanie LLM i walidacja Pydantic, atomowe wersjonowanie (`v1.0-gemini`, `v2.0-gemini`), zarządzanie unikalną flagą `active=True`, audyt historii wersji oraz mechanizm ręcznej korekty (`v1.1-manual`) wraz z rejestracją notatki zmiany (`change_note`).
    - Zaimplementowano endpointy REST API (`app/api/v1/profile.py`): `GET /api/profile`, `POST /api/profile/generate`, `GET /api/profile/versions`, `GET /api/profile/versions/{version}`, `PUT /api/profile` oraz `POST /api/profile/versions/{version}/activate`.
    - Rozszerzono zestaw testów automatycznych do **58 testów** (`pytest`) przechodzących w 100%, z pokryciem testowym schematów, klienta LLM (mock transport), serwisu gustu oraz endpointów API.
  - Zrealizowano i przetestowano **Etap 3 (Rekomendacje)**:
    - Zaimplementowano asynchronicznego klienta TMDB API (`app/integrations/tmdb.py`) obsługującego uwierzytelnianie kluczem API v3 oraz bearer tokenem v4, throttling (20 req/s), automatyczne ponawianie z wykładniczym backoffem oraz pobieranie rekomendacji, odkrywanie gatunkowe i powiązania z reżyserami/twórcami.
    - Zaimplementowano moduł agregacji kandydatów (`app/services/discovery.py`) realizujący podział puli: 40% podobne do ulubionych, 35% preferowane gatunki z aktywnego profilu gustu, 15% pozycje od ulubionych reżyserów oraz 10% kontrolowana eksploracja, z normalizacją metadanych do `CandidateItem`.
    - Zaimplementowano filtr anty-rekomendacji (`AntiRecommendationFilter` w `app/services/recommendations.py`) gwarantujący bezwzględne wykluczenie pozycji obejrzanych (`completed`, `watching`), znajdujących się na Plan to Watch, odrzuconych w przeszłości (`rejected`) oraz rekomendowanych w ciągu ostatnich 28 dni, a także wykluczanie animacji w oparciu o `anti_preferences`.
    - Zaimplementowano ranking regułowy (`RuleBasedRanker`), ocenę semantyczną LLM (`SemanticScorer`) z ustrukturyzowanym formatem JSON (`LLMEvaluationBatchResponse`: match_score, confidence, czynniki pozytywne, ryzyka, uzasadnienie) oraz serwis dywersyfikacji (`DiversificationService`) z limitem maks. 2 pozycji tego samego twórcy.
    - Zaimplementowano domenowy serwis `RecommendationService` orkiestrujący cały pipeline, transakcyjny zapis/upsert w SQLite (`MediaItem`, `RecommendationRun`, `Recommendation`) oraz endpointy REST API w `app/api/v1/recommendations.py` (`POST /api/recommendation-runs`, `GET /api/recommendation-runs/{run_id}`, `GET /api/recommendation-runs`).
    - Rozszerzono zestaw testów automatycznych do **72 testów** (`pytest`) przechodzących w 100% z pełną zgodnością lintera `ruff`.
  - Zrealizowano i przetestowano **Etap 4 (Panel i zatwierdzanie)**:
    - Zaimplementowano schematy Pydantic (`app/schemas/decision.py`) oraz rozszerzono `RecommendationRead` o `latest_decision` i `MediaItemSummary` o `poster_path`.
    - Zaimplementowano `DecisionService` (`app/services/decisions.py`) do rejestracji decyzji (`accept`, `reject`, `seen`, `later`) z aktualizacją statusów i tabeli audytowej `user_decisions` oraz oznaczaniem pozycji `seen` w `watch_history`.
    - Rozbudowano `WatchlistService` o metodę `add_approved_recommendations`: rygorystyczna weryfikacja statusu `accepted`, grupowanie na filmy i seriale, idempotentne pomijanie pozycji `added`, zapis do Simkl Plan to Watch i transakcyjna aktualizacja bazy.
    - Wdrożono endpointy REST API (`app/api/v1/decisions.py`): `POST /api/recommendations/decisions`, `POST /api/recommendations/approve`, `GET /api/recommendations/decisions` oraz `GET /api/recommendations/latest`.
    - Zbudowano nowoczesny, responsywny panel webowy SPA (`frontend/index.html`, `frontend/styles.css`, `frontend/app.js`) serwowany bezpośrednio przez FastAPI bez zewnętrznych zależności.
    - Rozszerzono zestaw testów automatycznych do **86 testów** (`pytest`) przechodzących w 100% z pełną zgodnością lintera i formatera `ruff`.
  - Zrealizowano i przetestowano **Etap 5 (MCP i harmonogram)**:
    - Zaimplementowano serwer MCP w standardzie `mcp>=2.0.0` (`app/mcp/server.py`) z pełnym zestawem 8 narzędzi domenowych: `get_taste_profile`, `get_library_stats`, `sync_simkl`, `generate_recommendations`, `get_recommendations`, `record_decision`, `approve_recommendations`, `get_recommendation_history`.
    - Zaimplementowano punkt wejścia CLI STDIO (`app/mcp/cli.py`) dla lokalnych klientów MCP (Antigravity IDE / CLI, Claude Desktop, Cursor).
    - Zintegrowano transport SSE / Streamable HTTP (`/mcp/sse`, `/mcp/messages/`) z dedykowanym middleware autoryzacyjnym `MCPAuthMiddleware` chroniącym endpoint tokenem `MCP_API_KEY` (dla ChatGPT / zdalnych asystentów).
    - Zaimplementowano harmonogram `AsyncIOScheduler` (`app/core/scheduler.py`) z cotygodniowym zadaniem synchronizacji i generowania nowej edycji oraz endpointy REST w `app/api/v1/scheduler.py` (`GET /api/scheduler/status`, `POST /api/scheduler/trigger`).
    - Rozszerzono zestaw testów automatycznych do **103 testów** (`pytest`) przechodzących w 100% z pełną zgodnością lintera i formatera `ruff`.
- **Kluczowe moduły**:
  - `app/main.py` — fabryka aplikacji FastAPI, montowanie SSE MCP (`/mcp`), serwowanie frontendu, lifespan, middleware i obsługa błędów
  - `app/core/` — konfiguracja Pydantic Settings, silnik bazy SQLite, harmonogram (`scheduler.py`) i logowanie
  - `app/models/` — modele SQLAlchemy 2.0 (`media_items`, `watch_history`, `taste_profiles`, `recommendation_runs`, `recommendations`, `user_decisions`, itp.)
  - `app/mcp/` — adapter Model Context Protocol (`server.py`, `cli.py`)
  - `app/integrations/simkl.py` — asynchroniczny klient API Simkl
  - `app/integrations/tmdb.py` — asynchroniczny klient API TMDB v3/v4
  - `app/integrations/llm/` — adaptery LLM (`LLMProvider`, `GeminiLLMClient`)
  - `app/schemas/` — schematy Pydantic (`taste.py`, `recommendation.py`, `sync.py`, `decision.py`)
  - `app/services/sync.py` — synchronizacja przyrostowa z Simkl do SQLite
  - `app/services/watchlist.py` — kontrolowany i idempotentny zapis pozycji do Simkl
  - `app/services/taste.py` — analiza historii, wersjonowanie profilu i ręczna korekta
  - `app/services/discovery.py` — zasilanie puli kandydatów z TMDB
  - `app/services/recommendations.py` — filtry anty-rekomendacji, ranking, ocena LLM, dywersyfikacja i rejestracja przebiegów
  - `app/services/decisions.py` — rejestracja decyzji użytkownika i historia
  - `app/api/` — endpointy REST (w tym `/api/health`, `/api/sync/simkl`, `/api/profile`, `/api/recommendation-runs`, `/api/recommendations/*`, `/api/scheduler/*`)
  - `frontend/` — lekki interfejs użytkownika (SPA HTML5 + CSS Grid + Vanilla JS)
  - `migrations/` — migracje bazy danych Alembic
  - `scripts/poc_taste_engine.py` — samodzielny skrypt badawczy PoC
  - `scripts/get_simkl_token.py` — asystent autoryzacji OAuth 2.0 Simkl Device Flow
  - `tests/` — testy jednostkowe i integracyjne (103 testy)
  - `data/` — lokalna baza SQLite i pliki wyjściowe

## Najbliższy Krok (Next Action)

> Przeprowadzić weryfikację integracji MCP na żywo w Antigravity/ChatGPT oraz zaplanować funkcje po-MVP (powiadomienia Pushover, analiza zmian gustu).

## Blokady (Blockers)

Brak. Wszystkie etapy MVP (PoC, 0, 1, 2, 3, 4, 5) są w pełni zaimplementowane i przetestowane.

## Backlog Zadań

### Etap PoC: Simkl Taste Engine (walidacja koncepcji)
- [x] Przygotowanie szablonu `.env.example` (zmienne dla Simkl i Gemini API) oraz konfiguracji `pyproject.toml` (`uv`)
- [x] Implementacja skryptu `scripts/poc_taste_engine.py` do pobrania historii Simkl
- [x] Generowanie profilu gustu i 10 filmów + 5 seriali przez Gemini
- [x] Ewaluacja jakości wygenerowanych rekomendacji przez użytkownika

### Etap 0: Fundament
- [x] Inicjalizacja repozytorium i struktury `app/`
- [x] FastAPI, SQLite i migracje schematu bazy wg `DATA_MODEL.md`
- [x] Logowanie, obsługa błędów, konfiguracja sekretów z walidacją Pydantic Settings
- [x] Konfiguracja testów `pytest` i reguł `ruff`

### Etap 1: Simkl
- [x] Klient API Simkl i obsługa uwierzytelniania
- [x] Pobieranie historii, ocen i listy Plan to Watch
- [x] Przyrostowa synchronizacja do SQLite
- [x] Idempotentny zapis zaakceptowanych pozycji z testami

### Etap 2: Profil gustu
- [x] Serwis analizy historii i preferencji
- [x] Generowanie i wersjonowanie profilu JSON (wagi, confidence)
- [x] Możliwość ręcznej korekty profilu

### Etap 3: Rekomendacje
- [x] Integracja z TMDB (wyszukiwanie kandydatów, metadane)
- [x] Filtry anty-rekomendacji (obejrzane, Plan to Watch, odrzucone)
- [x] Ranking regułowy + ocena semantyczna LLM
- [x] Dywersyfikacja wyników i rejestracja przebiegu w bazie

### Etap 4: Panel i zatwierdzanie
- [x] Minimalny UI do przeglądu propozycji
- [x] Rejestracja decyzji użytkownika (`accept`, `reject`, `seen`, `later`)
- [x] Idempotentne, kontrolowane dodawanie zaakceptowanych pozycji do Simkl
- [x] Historia przebiegów i decyzji

### Etap 5: MCP i harmonogram
- [x] Narzędzia MCP STDIO dla Antigravity (`app/mcp/server.py`, `app/mcp/cli.py`)
- [x] MCP HTTPS/Streamable dla ChatGPT (`/mcp/sse`, `/mcp/messages/`, `MCPAuthMiddleware`)
- [x] Scheduler dla cotygodniowego generowania propozycji (`app/core/scheduler.py`, `app/api/v1/scheduler.py`)
- [x] Monitoring i endpointy zarządzania harmonogramem

## Rejestr Decyzji (ADR)

### 2026-11-06 — Inicjalizacja wzorca deweloperskiego
- **Decyzja / Zmiana**: Przygotowano wzorcową strukturę z podziałem na operacyjny kodeks `GEMINI.md` oraz dynamiczny rejestr stanu `PROJECT.md`.
- **Uzasadnienie**: Zapewnienie powtarzalnego, bezpiecznego cyklu wytwórczego AI-first.

### 2026-11-14 — Wdrożenie Etapu PoC i wybór stosu technologicznego
- **Decyzja / Zmiana**:
  1. Zdefiniowano i wprowadzono **Etap PoC (Simkl Taste Engine)** przed formalnym Etapem 0 architektury produkcyjnej.
  2. Wybrano `uv` jako menedżer pakietów, `pyproject.toml`, `ruff` jako linter/formatter oraz `pytest` do testów.
  3. Jako wiodący model LLM dla etapu PoC wybrano `Gemini` (Google GenAI SDK), z architekturą docelową wspierającą OpenAI.
  4. PoC zostanie zrealizowany w formie niezależnego skryptu badawczego `scripts/poc_taste_engine.py`, pobierającego dane z Simkl i zapisującego wygenerowane propozycje do pliku JSON.
- **Uzasadnienie**: Umożliwienie natychmiastowej ewaluacji jakości algorytmu promptowania i profilu gustu bez konieczności przedwczesnej budowy pełnego serwera API i bazy danych.

### 2026-11-14 — Zakończenie Etapu PoC i wnioski z profilowania gustu
- **Decyzja / Zmiana**:
  1. Pomyślnie zweryfikowano i zaakceptowano działanie silnika profilowania LLM (Gemini 2.5 Flash) na rzeczywistych danych konta Simkl użytkownika.
  2. Zaimplementowano obsługę autoryzacji Simkl Auth V2 (RFC 8628 Device Flow) w dedykowanym asystencie `scripts/get_simkl_token.py`.
  3. Zaimplementowano dynamiczne auto-wykrywanie modeli w `GeminiProvider`.
  4. Potwierdzono trafność opisu profilu gustu użytkownika (orientacja na Crime, Drama, Thriller, Historical Realism, moralną niejednoznaczność i wyrazistych reżyserów).
  5. **Wniosek do Etapu 3 (Rekomendacje)**: Pula kandydatów w PoC zawierała sztywną listę tytułów (stąd obecność animacji *Scavengers Reign* oraz nadmiaru sci-fi). W docelowym silniku kandydaci będą pobierani dynamicznie z TMDB z uwzględnieniem preferencji dotyczących wykluczania animacji oraz zachowania właściwych proporcji gatunkowych.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu PoC z ROADMAP.md i formalne przejście do prac nad Etapem 0 (Fundament).

### 2026-11-14 — Wdrożenie Etapu 0 (Fundament)
- **Decyzja / Zmiana**:
  1. Zaimplementowano szkielet backendu w `FastAPI` ze strukturą modułową w katalogu `app/`.
  2. Wprowadzono `pydantic-settings` do walidacji konfiguracji oraz `SecretStr` do ochrony wrażliwych tokenów przed wyciekiem w logach.
  3. Wybrano `SQLAlchemy 2.0` (z typowaniem `Mapped`) oraz `Alembic` do zarządzania bazą `SQLite` (`DATA_MODEL.md`), z wymuszeniem `PRAGMA foreign_keys=ON` i renderowaniem migracji w trybie batchowym.
  4. Zaimplementowano globalne mapowanie błędów na kody z `API_CONTRACTS.md` oraz middleware korelacji `X-Request-ID`.
  5. Pokryto fundament 16 testami automatycznymi (`pytest`) oraz skonfigurowano sprawdzanie reguł jakości kodu `ruff`.
- **Uzasadnienie**: Zapewnienie stabilnej, skalowalnej i przetestowanej bazy architektonicznej dla integracji z Simkl (Etap 1).

### 2026-11-14 — Wdrożenie Etapu 1 (Simkl Integration & Sync)
- **Decyzja / Zmiana**:
  1. Zaimplementowano asynchroniczny klient `SimklClient` (`app/integrations/simkl.py`) z obsługą nagłówków API, throttlingiem (10 GET/s, 1 POST/s) i retry z wykładniczym backoffem.
  2. Zapewniono obsługę obu wariantów zmiennej tokenu (`SIMKL_USER_TOKEN` oraz `SIMKL_ACCESS_TOKEN`) w `Settings.effective_simkl_token`.
  3. Zaimplementowano `SyncService` (`app/services/sync.py`) obsługujący zarówno synchronizację pełną, jak i przyrostową (`sync_state.last_success_at` -> parametr `date_from`), mapowanie i upsert do `media_items` i `watch_history` oraz zarządzanie transakcjami.
  4. Zaimplementowano `WatchlistService` (`app/services/watchlist.py`) ze ścisłą egzekucją reguły bezpieczeństwa (brak zapisu bez jawnej akceptacji `status == 'accepted'`) oraz pełną idempotencją zapisu do Simkl (`POST /sync/add-to-list`).
  5. Dodano endpointy REST API: `POST /api/sync/simkl` oraz `GET /api/sync/simkl/status` z wstrzykiwaniem zależności `Annotated[Session, Depends(get_db)]`.
  6. Dodano zestaw testów automatycznych (łącznie 32 testy przechodzące w 100%), mockujący transport HTTP bez zewnętrznych bibliotek (wbudowany `httpx.MockTransport`).
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 1 z ROADMAP.md: rzeczywiste dane są poprawnie pobierane i zapisywane lokalnie, a zapis do Simkl jest kontrolowany i idempotentny.

### 2026-11-14 — Wdrożenie Etapu 2 (Taste Profile Engine & Versioning)
- **Decyzja / Zmiana**:
  1. Zaimplementowano rygorystyczne schematy Pydantic (`app/schemas/taste.py`) z rozdzieleniem wagi cechy (`weight`) od pewności modelu (`confidence`), rozdzieleniem zainteresowań stałych i chwilowych oraz metadanymi proweniencji.
  2. Utworzono moduł adaptera LLM (`app/integrations/llm/`) z protokołem `LLMProvider` i asynchronicznym klientem `GeminiLLMClient`, z trybem `response_mime_type="application/json"` oraz automatycznym fallbackiem wersji modeli (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`).
  3. Zaimplementowano `TasteService` (`app/services/taste.py`): agregacja historii z bazy, powiązanie ze znacznikiem `based_on_sync_at` synchronizacji Simkl, atomowe wersjonowanie (`v1.0-gemini`, `v2.0-gemini`), zarządzanie unikalną flagą `active=True` oraz audyt historii wersji.
  4. Wprowadzono mechanizm ręcznej korekty (`adjust_profile`), generujący nowe wersje manualne (np. `v1.1-manual`) i rejestrujący notatki modyfikacji (`change_note`).
  5. Dodano pełny zestaw endpointów REST API: `GET /api/profile`, `POST /api/profile/generate`, `GET /api/profile/versions`, `GET /api/profile/versions/{version}`, `PUT /api/profile` oraz `POST /api/profile/versions/{version}/activate`.
  6. Rozszerzono zestaw testów automatycznych do 58 testów przechodzących w 100% (`pytest`) oraz pełną zgodność lintera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 2 z ROADMAP.md: profil ma uzasadnienie i można jednoznacznie odtworzyć, z jakich danych powstał, a użytkownik ma pełną kontrolę i możliwość ręcznej modyfikacji wag i reguł.

### 2026-11-14 — Wdrożenie Etapu 3 (Recommendation Engine, TMDB & Scoring)
- **Decyzja / Zmiana**:
  1. Zaimplementowano klienta `TMDBClient` (`app/integrations/tmdb.py`) z obsługą autoryzacji kluczem v3 oraz tokenem v4, throttlingiem (20 req/s), automatycznym ponawianiem z wykładniczym backoffem i hierarchią wyjątków `TMDBError`.
  2. Zbudowano moduł `DiscoveryService` (`app/services/discovery.py`) pozyskujący pulę kandydatów z 4 strategii: 40% rekomendacje do ulubionych, 35% preferowane gatunki, 15% ulubieni twórcy, 10% eksploracja wysokiej jakości.
  3. Wprowadzono `AntiRecommendationFilter` wykluczający pozycje obejrzane (`completed`, `watching`), znajdujące się na Plan to Watch, odrzucone w przeszłości oraz rekomendowane w ostatnich 28 dniach, wraz z wykluczaniem animacji w oparciu o antypreferencje i parametry zapytania.
  4. Wdrożono wstępny ranking regułowy (`RuleBasedRanker`), selekcję top kandydatów (25 filmów, 15 seriali) i ocenę semantyczną LLM (`SemanticScorer`) z walidacją ustrukturyzowanego schematu Pydantic (`LLMEvaluationBatchResponse`).
  5. Zaimplementowano `DiversificationService` ograniczający maks. 2 pozycje tego samego reżysera w przebiegu oraz finalną selekcję 10 filmów i 5 seriali.
  6. Utworzono `RecommendationService` orkiestrujący przebiegi i transakcyjnie zapisujący do SQLite (`RecommendationRun`, `Recommendation`, `MediaItem`) oraz endpointy REST API: `POST /api/recommendation-runs`, `GET /api/recommendation-runs/{run_id}`, `GET /api/recommendation-runs`.
  7. Rozszerzono testy automatyczne do **72 testów** (`pytest`) przechodzących w 100% oraz pełną zgodność lintera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 3 z ROADMAP.md: system tworzy powtarzalne, weryfikowalne listy 10 filmów i 5 seriali bez duplikatów i z pełnymi uzasadnieniami, bez ingerencji w Simkl bez akceptacji użytkownika.

### 2026-11-14 — Wdrożenie Etapu 4 (Panel i zatwierdzanie)
- **Decyzja / Zmiana**:
  1. Zdefiniowano i zaimplementowano schematy Pydantic (`app/schemas/decision.py`) dla operacji jednostkowych i zbiorczych: `SingleDecisionRequest`, `DecisionBatchRequest`, `UserDecisionRead`, `DecisionBatchResponse`, `ApproveBatchRequest`, `ApproveBatchResponse`.
  2. Rozszerzono `RecommendationRead` o `latest_decision` oraz `MediaItemSummary` o `poster_path`.
  3. Zaimplementowano domenowy serwis `DecisionService` (`app/services/decisions.py`) do rejestracji decyzji (`accept`, `reject`, `seen`, `later`), aktualizacji statusów w tabeli `recommendations`, audytu w tabeli `user_decisions` oraz aktualizacji lokalnej historii (`watch_history(status='completed')` dla decyzji `seen`).
  4. Rozbudowano `WatchlistService` (`app/services/watchlist.py`) o metodę `add_approved_recommendations`:
     - egzekwowanie nienegocjowalnej reguły bezpieczeństwa: dozwolony zapis wyłącznie pozycji o statusie `accepted`,
     - pełna idempotencja: pozycje o statusie `added` są raportowane jako `already_added` bez wywoływania API Simkl,
     - optymalizacja zapisu: automatyczne rozdzielanie pozycji na filmy (`movies`) i seriale (`shows`) oraz batching do Simkl `add-to-list`.
  5. Dodano dedykowane endpointy REST API w `app/api/v1/decisions.py`: `POST /api/recommendations/decisions`, `POST /api/recommendations/approve`, `GET /api/recommendations/decisions` oraz `GET /api/recommendations/latest`.
  6. Rozszerzono `AntiRecommendationFilter` o wykluczanie z kolejnych rekomendacji pozycji, dla których zarejestrowano decyzję `seen` lub status `seen`.
  7. Zaimplementowano nowoczesny, responsywny panel webowy (SPA w HTML5 + CSS Grid + Vanilla JS) w katalogu `frontend/`, serwowany bezpośrednio przez FastAPI bez zewnętrznych zależności.
  8. Rozszerzono zestaw testów automatycznych do **86 testów** (`pytest`) przechodzących w 100% oraz pełną zgodność lintera i formatera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 4 z ROADMAP.md: pełny przepływ od listy propozycji do Plan to Watch działa bez automatycznego zapisu, z pełną kontrolą użytkownika i audytem decyzji.

### 2026-11-14 — Wdrożenie Etapu 5 (MCP Server & Harmonogram)
- **Decyzja / Zmiana**:
  1. Zaimplementowano adapter Model Context Protocol (`mcp>=2.0.0`) w katalogu `app/mcp/`:
     - `app/mcp/server.py` definiujący instancję `MCPServer` z 8 narzędziami domenowymi (`get_taste_profile`, `get_library_stats`, `sync_simkl`, `generate_recommendations`, `get_recommendations`, `record_decision`, `approve_recommendations`, `get_recommendation_history`).
     - Twarde zabezpieczenie operacji zapisu: `approve_recommendations` rygorystycznie deleguje do `WatchlistService.add_approved_recommendations`, co uniemożliwia modelom LLM bezpośredni zapis bez uprzedniej decyzji `accept`.
     - `app/mcp/cli.py` jako punkt wejścia STDIO dla lokalnych asystentów AI (Antigravity IDE / CLI, Claude Desktop, Cursor).
  2. Zintegrowano transport SSE / Streamable HTTP (`/mcp/sse`, `/mcp/messages/`) w aplikacji FastAPI (`app/main.py`):
     - Zaimplementowano middleware `MCPAuthMiddleware` chroniące endpoint kluczem `MCP_API_KEY` (Bearer header lub query param `?api_key=...`).
     - Wyłączono restrykcję DNS rebindingu w SSE dla obsługi proxy/tunelowania i środowisk testowych.
  3. Zaimplementowano asynchroniczny harmonogram `AsyncIOScheduler` (`app/core/scheduler.py`):
     - Zarządzanie cyklem życia w `lifespan` FastAPI (`start_scheduler`, `stop_scheduler`).
     - Cotygodniowy job synchronizujący Simkl i generujący świeżą edycję 10 filmów i 5 seriali (`mode='weekly'`).
     - Dodano endpointy REST w `app/api/v1/scheduler.py` (`GET /api/scheduler/status`, `POST /api/scheduler/trigger`).
  4. Rozszerzono zestaw testów automatycznych do **103 testów** (`pytest`) z wynikiem 100% sukcesu oraz pełną czystością lintera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 5 z ROADMAP.md: oba interfejsy (lokalny STDIO dla Antigravity oraz zdalny SSE dla ChatGPT) korzystają z tych samych serwisów domenowych, tej samej bazy SQLite i tego samego profilu gustu bez duplikowania logiki.
