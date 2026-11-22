# Rejestr Decyzji Architektonicznych (ADR)

Ten dokument zawiera historię kluczowych decyzji projektowych, technologicznych i operacyjnych podjętych w trakcie rozwoju systemu Curato.

---

### 2026-11-06 — Inicjalizacja wzorca deweloperskiego
- **Decyzja / Zmiana**: Przygotowano wzorcową strukturę z podziałem na reguły operacyjne agentów (`AGENTS.md`) oraz dynamiczny rejestr stanu i etapów.
- **Uzasadnienie**: Zapewnienie powtarzalnego, bezpiecznego cyklu wytwórczego AI-first z poszanowaniem zasad TDD i spójności architektury.

---

### 2026-11-14 — Wdrożenie Etapu PoC i wybór stosu technologicznego
- **Decyzja / Zmiana**:
  1. Zdefiniowano i wprowadzono **Etap PoC (Simkl Taste Engine)** przed formalnym Etapem 0 architektury produkcyjnej.
  2. Wybrano `uv` jako menedżer pakietów, `pyproject.toml`, `ruff` jako linter/formatter oraz `pytest` do testów.
  3. Jako wiodący model LLM dla etapu PoC wybrano `Gemini` (Google GenAI SDK), z architekturą docelową wspierającą OpenAI.
  4. PoC zrealizowano w formie niezależnego skryptu badawczego `scripts/poc_taste_engine.py`, pobierającego dane z Simkl i zapisującego wygenerowane propozycje do pliku JSON.
- **Uzasadnienie**: Umożliwienie natychmiastowej ewaluacji jakości algorytmu promptowania i profilu gustu bez konieczności przedwczesnej budowy pełnego serwera API i bazy danych.

---

### 2026-11-14 — Zakończenie Etapu PoC i wnioski z profilowania gustu
- **Decyzja / Zmiana**:
  1. Pomyślnie zweryfikowano i zaakceptowano działanie silnika profilowania LLM (Gemini 2.5 Flash) na rzeczywistych danych konta Simkl użytkownika.
  2. Zaimplementowano obsługę autoryzacji Simkl Auth V2 (RFC 8628 Device Flow) w dedykowanym asystencie `scripts/get_simkl_token.py`.
  3. Zaimplementowano dynamiczne auto-wykrywanie modeli w `GeminiProvider`.
  4. Potwierdzono trafność opisu profilu gustu użytkownika (orientacja na Crime, Drama, Thriller, Historical Realism, moralną niejednoznaczność i wyrazistych reżyserów).
  5. **Wniosek do Etapu 3 (Rekomendacje)**: Pula kandydatów w PoC zawierała sztywną listę tytułów (stąd obecność animacji *Scavengers Reign* oraz nadmiaru sci-fi). W docelowym silniku kandydaci są pobierani dynamicznie z TMDB z uwzględnieniem preferencji dotyczących wykluczania animacji oraz zachowania właściwych proporcji gatunkowych.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu PoC z ROADMAP.md i formalne przejście do prac nad Etapem 0 (Fundament).

---

### 2026-11-14 — Wdrożenie Etapu 0 (Fundament)
- **Decyzja / Zmiana**:
  1. Zaimplementowano szkielet backendu w `FastAPI` ze strukturą modułową w katalogu `app/`.
  2. Wprowadzono `pydantic-settings` do walidacji konfiguracji oraz `SecretStr` do ochrony wrażliwych tokenów przed wyciekiem w logach.
  3. Wybrano `SQLAlchemy 2.0` (z typowaniem `Mapped`) oraz `Alembic` do zarządzania bazą `SQLite` (`DATA_MODEL.md`), z wymuszeniem `PRAGMA foreign_keys=ON` i renderowaniem migracji w trybie batchowym.
  4. Zaimplementowano globalne mapowanie błędów na kody z `API_CONTRACTS.md` oraz middleware korelacji `X-Request-ID`.
  5. Pokryto fundament 16 testami automatycznymi (`pytest`) oraz skonfigurowano sprawdzanie reguł jakości kodu `ruff`.
- **Uzasadnienie**: Zapewnienie stabilnej, skalowalnej i przetestowanej bazy architektonicznej dla integracji z Simkl (Etap 1).

---

### 2026-11-14 — Wdrożenie Etapu 1 (Simkl Integration & Sync)
- **Decyzja / Zmiana**:
  1. Zaimplementowano asynchroniczny klient `SimklClient` (`app/integrations/simkl.py`) z obsługą nagłówków API, throttlingiem (10 GET/s, 1 POST/s) i retry z wykładniczym backoffem.
  2. Zapewniono obsługę obu wariantów zmiennej tokenu (`SIMKL_USER_TOKEN` oraz `SIMKL_ACCESS_TOKEN`) w `Settings.effective_simkl_token`.
  3. Zaimplementowano `SyncService` (`app/services/sync.py`) obsługujący zarówno synchronizację pełną, jak i przyrostową (`sync_state.last_success_at` -> parametr `date_from`), mapowanie i upsert do `media_items` i `watch_history` oraz zarządzanie transakcjami.
  4. Zaimplementowano `WatchlistService` (`app/services/watchlist.py`) ze ścisłą egzekucją reguły bezpieczeństwa (brak zapisu bez jawnej akceptacji `status == 'accepted'`) oraz pełną idempotencją zapisu do Simkl (`POST /sync/add-to-list`).
  5. Dodano endpointy REST API: `POST /api/sync/simkl` oraz `GET /api/sync/simkl/status` z wstrzykiwaniem zależności `Annotated[Session, Depends(get_db)]`.
  6. Dodano zestaw testów automatycznych (łącznie 32 testy przechodzące w 100%), mockujący transport HTTP bez zewnętrznych bibliotek (wbudowany `httpx.MockTransport`).
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 1 z ROADMAP.md: rzeczywiste dane są poprawnie pobierane i zapisywane lokalnie, a zapis do Simkl jest kontrolowany i idempotentny.

---

### 2026-11-14 — Wdrożenie Etapu 2 (Taste Profile Engine & Versioning)
- **Decyzja / Zmiana**:
  1. Zaimplementowano rygorystyczne schematy Pydantic (`app/schemas/taste.py`) z rozdzieleniem wagi cechy (`weight`) od pewności modelu (`confidence`), rozdzieleniem zainteresowań stałych i chwilowych oraz metadanymi proweniencji.
  2. Utworzono moduł adaptera LLM (`app/integrations/llm/`) z protokołem `LLMProvider` i asynchronicznym klientem `GeminiLLMClient`, z trybem `response_mime_type="application/json"` oraz automatycznym fallbackiem wersji modeli (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`).
  3. Zaimplementowano `TasteService` (`app/services/taste.py`): agregacja historii z bazy, powiązanie ze znacznikiem `based_on_sync_at` synchronizacji Simkl, atomowe wersjonowanie (`v1.0-gemini`, `v2.0-gemini`), zarządzanie unikalną flagą `active=True` oraz audyt historii wersji.
  4. Wprowadzono mechanizm ręcznej korekty (`adjust_profile`), generujący nowe wersje manualne (np. `v1.1-manual`) i rejestrujący notatki modyfikacji (`change_note`).
  5. Dodano pełny zestaw endpointów REST API: `GET /api/profile`, `POST /api/profile/generate`, `GET /api/profile/versions`, `GET /api/profile/versions/{version}`, `PUT /api/profile` oraz `POST /api/profile/versions/{version}/activate`.
  6. Rozszerzono zestaw testów automatycznych do 58 testów przechodzących w 100% (`pytest`) oraz pełną zgodność lintera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 2 z ROADMAP.md: profil ma uzasadnienie i można jednoznacznie odtworzyć, z jakich danych powstał, a użytkownik ma pełną kontrolę i możliwość ręcznej modyfikacji wag i reguł.

---

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

---

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

---

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

---

### 2026-11-14 — Definicja etapów po-MVP: Zwiastuny, Proxmox oraz Open-Source / Docker Hub
- **Decyzja / Zmiana**:
  1. Zaplanowano **Etap 6 (Zwiastuny i optymalizacja współbieżności bazy WAL)**: integracja TMDB Videos (`/movie/{id}/videos`, `/tv/{id}/videos`), modal odtwarzacza YouTube (`youtube-nocookie`) bezpośrednio w panelu webowym, zrównoleglenie pobierania kandydatów TMDB (`asyncio.gather`) oraz włączenie trybu SQLite WAL (`PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;`) pod kątem stabilnej pracy 24/7.
  2. Zaplanowano **Etap 7 (Konteneryzacja i wdrożenie na Proxmox)**: wieloetapowy `Dockerfile` z użytkownikiem nieuprzywilejowanym, skrypt startowy `entrypoint.sh` wykonujący automatyczne migracje `alembic upgrade head`, konfiguracja `docker-compose.yml` z wolumenem danych bazy oraz procedura uruchomienia w kontenerze LXC Debian z Dockerem pod Proxmox VE.
  3. Zaplanowano **Etap 8 (Przygotowanie repozytorium do upublicznienia na GitHub i Docker Hub)**: audyt bezpieczeństwa sekretów, profesjonalna dokumentacja `README.md`, licencja MIT, szablony GitHub oraz workflow GitHub Actions CI/CD automatycznie testujący kod i publikujący wieloarchitektoniczne obrazy na Docker Hub.
- **Uzasadnienie**: Ustalenie jasnego planu przejścia projektu z fazy lokalnego MVP do niezawodnej, stale działającej domowej mikro-usługi na Proxmoxie oraz publicznego projektu Open Source.

---

### 2026-11-14 — Wdrożenie wytycznych dla agentów i wzorców wdrożeniowych Proxmox/Docker
- **Decyzja / Zmiana**:
  1. Zaktualizowano `AGENTS.md` o precyzyjną regułę izolacji sesji bazy SQLite w zadaniach asynchronicznych i tle (zapobieganie wyciekom sesji i blokadom bazy przy współbieżności) oraz wymóg stosowania wyłącznie wbudowanego `httpx.MockTransport` w testach jednostkowych.
  2. Utworzono dokumentację wdrożeniową `docs/deployment.md` definiującą procedurę uprawnień wolumenów SQLite WAL (UID 1000 `appuser`), automatycznych migracji Alembic w `entrypoint.sh` oraz bezbuforowej konfiguracji Reverse Proxy (Caddy/Nginx) dla streamingu SSE serwera MCP (ChatGPT).
- **Uzasadnienie**: Zapewnienie powtarzalnych wzorców pracy dla inżynierów i agentów AI.

---

### 2026-11-14 — Strategia repozytoriów (GitHub Primary + Gitea Mirror) i rezygnacja z Docker Hub
- **Decyzja / Zmiana**:
  1. **Rezygnacja z publikacji na Docker Hub**: Projekt jest dedykowanym, jednoosobowym systemem (bespoke/single-user) z wrażliwymi tokenami OAuth, specyficznym anty-filtrem i serwerem MCP. Publiczny obraz na Docker Hub niósłby ryzyko narzutu utrzymaniowego (CVE, multi-arch) oraz konieczność budowy multi-tenancy. Kontenery są budowane lokalnie na serwerze Proxmox (`docker compose build`) z wykorzystaniem cache i `uv`.
  2. **GitHub jako Primary / Single Source of Truth**: Kod źródłowy jest publikowany na GitHubie jako wzorcowe portfolio i referencyjna implementacja MCP + LLM + FastAPI z darmowym CI/CD (GitHub Actions dla `pytest` i `ruff`).
  3. **Mitygacja ryzyk GitHuba**: Wyłączenie sekcji Issues i Pull Requests w ustawieniach repozytorium (ochrona przed narzutem obsługi społeczności), bezwzględne ignorowanie bazy i danych (`/data/`) oraz publikacja czystej historii w standardzie Conventional Commits.
  4. **Własna Gitea jako Pasywny Mirror (Pull Mirror)**: Gitea w homelabie automatycznie ściąga commity z GitHuba. Służy jako suwerenny backup off-cloud oraz punkt pobierania kodu przez Proxmox w sieci LAN bez zależności od łącza internetowego.
- **Uzasadnienie**: Maksymalizacja korzyści inżynierskich i portfolio przy jednoczesnym wyeliminowaniu narzutu operacyjnego i ryzyk bezpieczeństwa.

---

### 2026-11-15 — Wdrożenie Etapu 6 (Zwiastuny, optymalizacja współbieżności WAL i MCP get_trailer)
- **Decyzja / Zmiana**:
  1. Włączono optymalizacje współbieżności SQLite pod pracę 24/7 (`PRAGMA foreign_keys=ON;`, `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;`, `PRAGMA synchronous=NORMAL;`), eliminując blokady bazy danych pomiędzy zapytaniami API, serwerem MCP a zadaniami schedulera w tle.
  2. Zaimplementowano pobieranie wideo zwiastunów w `TMDBClient` (`/movie/{id}/videos`, `/tv/{id}/videos`) z algorytmem `extract_best_trailer` priorytetyzującym oficjalne zwiastuny YouTube.
  3. Zrównoleglono agregację kandydatów w `DiscoveryService` za pomocą `asyncio.gather` z semaforem (`asyncio.Semaphore(5)`).
  4. Dodano pola `trailer_key` i `trailer_url` do schematów `CandidateItem`, `MediaItemSummary`, `RecommendationRead` oraz model `TrailerResponse`, zapisując metadane w `metadata_json` bez konieczności migracji schematu tabeli bazy danych.
  5. Wdrożono endpoint REST `GET /api/recommendations/{id}/trailer` oraz 9. narzędzie serwera MCP `get_trailer`, a także wzbogacono narzędzie `get_recommendations` o bezpośrednie linki do zwiastunów YouTube.
  6. Wdrożono odtwarzacz zwiastunów w UI SPA (`youtube-nocookie.com`, responsywny kontener 16:9, przycisk zwiastuna na kartach, natychmiastowe zatrzymywanie odtwarzania przy zamykaniu modala, fallback wyszukiwania).
  7. Rozszerzono zestaw testów automatycznych do **108 testów** (`pytest`) przechodzących w 100% oraz pełną zgodność lintera `ruff`.
- **Uzasadnienie**: Spełnienie kryteriów akceptacji Etapu 6 z ROADMAP.md: użytkownik może wygodnie obejrzeć zwiastun w przeglądarce przed podjęciem decyzji oraz poprosić o zwiastun asystenta MCP (Antigravity / ChatGPT), a baza SQLite działa bezkolizyjnie w trybie WAL.

---

### 2026-11-15 — Wdrożenie produkcyjne na serwerze Proxmox VE (r2d2)
- **Decyzja / Zmiana**:
  1. Utworzono dedykowany nieuprzywilejowany kontener LXC Debian 12 (CT 133 `curato`, 2 vCPU, 2 GB RAM, 15 GB na ZFS `fast-tank`) w VLAN 30 na Proxmoxie `r2d2`.
  2. Zainstalowano oficjalny pakiet Docker Engine i Docker Compose wewnątrz LXC z `nesting=1,keyctl=1`.
  3. Skonfigurowano uprawnienia wolumenu bazy SQLite WAL pod użytkownika `appuser` (UID 1000) oraz zsynchronizowano konfigurację produkcyjną `.env`.
  4. Wyeliminowano problem shebangu wirtualnego środowiska wieloetapowego Dockera (`WORKDIR /app` w etapie builder i `python -m alembic`) oraz zaktualizowano `uv.lock` o brakujące zależności etapu 5 (`apscheduler`, `mcp`, `sse-starlette`).
  5. Zweryfikowano działanie kontenera (status `healthy`, automatyczne migracje bazy SQLite, scheduler aktywny).
  6. Zintegrowano usługę z Reverse Proxy Caddy (CT 111 `caddy-proxy`) z przypisaniem IP `192.168.1.36` oraz domeną `https://curato.app.witkowski.xyz` i wyłączeniem buforowania (`flush_interval -1`).
  7. Zweryfikowano poprawność certyfikatu SSL, panelu Web UI oraz strumieniowania SSE endpointu MCP (`/mcp/sse`) z poprawną autoryzacją tokenem `MCP_API_KEY`.
- **Uzasadnienie**: Zakończenie pełnego cyklu wytwórczego i wdrożeniowego projektu: Curato działa stabilnie 24/7 jako mikro-usługa w homelabie z bezpiecznym dostępem dla ChatGPT i Antigravity.

---

### 2026-11-22 — Obsługa Simkl OAuth2 Refresh Token i automatyczne odświeżanie sesji
- **Decyzja / Zmiana**:
  1. Zidentyfikowano przyczynę wygasania tokenów Simkl po 7 dniach (standard Simkl Auth V2 ogranicza ważność `access_token` do 7 dni, oferując 180-dniowy `refresh_token` z mechanizmem *sliding window*).
  2. Zaimplementowano moduł `app/core/tokens.py` do trwałego przechowywania i odczytu tokenów w istniejącej tabeli SQLite `app_settings` (klucz `simkl_auth_tokens`) z automatyczną aktualizacją pliku `.env` w trybie deweloperskim.
  3. Zaktualizowano `SimklClient` (`app/integrations/simkl.py`) o metodę `refresh_access_token` oraz automatyczną detekcję wygaśnięcia tokena (kod HTTP 401/403) z natychmiastowym transparentnym odświeżeniem i ponowieniem zapytania bez przerywania operacji użytkownika.
  4. Dodano synchronizację tokenów między procesami/zadaniami w tle za pomocą `asyncio.Lock` oraz detekcję tokenów odświeżonych współbieżnie.
  5. Rozszerzono skrypt `scripts/get_simkl_token.py` o zapisywanie `refresh_token` do `.env` oraz do tabeli `app_settings` w lokalnej bazie danych SQLite.
  6. Rozszerzono testy automatyczne do **123 testów** (`pytest`) przechodzących w 100% oraz pełną zgodność lintera `ruff`.
- **Uzasadnienie**: Wyeliminowanie cyklicznych błędów autoryzacji `Access token has expired` i zapewnienie w pełni bezobsługowej pracy Curato 24/7.
