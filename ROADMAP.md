# Roadmap

## Etap PoC -- Simkl Taste Engine (walidacja koncepcji)

-   [x] Skrypt badawczy `scripts/poc_taste_engine.py` i konfiguracja `.env.example`.
-   [x] Połączenie z API Simkl i pobranie historii/ocen użytkownika.
-   [x] Analiza preferencji przez LLM (Google GenAI / Gemini).
-   [x] Wygenerowanie pierwszego profilu gustu w JSON.
-   [x] Wygenerowanie zestawu 10 rekomendacji filmów i 5 seriali z uzasadnieniami.
-   [x] Ręczna weryfikacja trafności rekomendacji przez użytkownika.

**Akceptacja:** wygenerowany plik JSON z profilem gustu oraz 10 filmami i 5 serialami oceniony jakościowo przez użytkownika przed budową pełnej architektury. (Ukończono pomyślnie)

## Etap 0 -- fundament

-   [x] Repozytorium, konfiguracja i struktura modułów.
-   [x] FastAPI, SQLite, migracje.
-   [x] Logowanie, obsługa błędów, konfiguracja sekretów.
-   [x] Testy i CI.

**Akceptacja:** aplikacja uruchamia się lokalnie, migracje i testy
przechodzą. (Ukończono pomyślnie)

## Etap 1 -- Simkl

-   [x] Rejestracja aplikacji i OAuth zgodny z aktualną dokumentacją.
-   [x] Odczyt historii, ocen i Plan to Watch.
-   [x] Lokalna synchronizacja przyrostowa.
-   [x] Test zapisu pojedynczej zaakceptowanej pozycji.

**Akceptacja:** rzeczywiste dane są poprawnie zapisane lokalnie; zapis
do Simkl jest kontrolowany i idempotentny. (Ukończono pomyślnie)

## Etap 2 -- profil gustu

-   [x] Analiza historii i ocen.
-   [x] Pierwszy profil JSON z wagami i confidence.
-   [x] Wersjonowanie i ręczna korekta profilu.

**Akceptacja:** profil ma uzasadnienie i można odtworzyć, z jakich
danych powstał. (Ukończono pomyślnie)

## Etap 3 -- rekomendacje

-   [x] Integracja TMDB.
-   [x] Generowanie i normalizacja kandydatów.
-   [x] Filtry obejrzanych, Plan to Watch i odrzuconych.
-   [x] Ranking regułowy i ocena LLM.
-   [x] Dywersyfikacja i zapis przebiegów.

**Akceptacja:** system tworzy listę 10 filmów i 5 seriali bez duplikatów
i z uzasadnieniami. (Ukończono pomyślnie)

## Etap 4 -- panel i zatwierdzanie

-   [x] Lista rekomendacji.
-   [x] Decyzje: zaakceptuj, odrzuć, już widziałem, później.
-   [x] Zbiorcze dodawanie zaakceptowanych do Simkl.
-   [x] Historia przebiegów i decyzji.

**Akceptacja:** pełny przepływ od listy do Plan to Watch działa bez
automatycznego zapisu. (Ukończono pomyślnie)

## Etap 5 -- MCP i harmonogram

-   [x] MCP STDIO dla Antigravity.
-   [x] MCP HTTPS dla ChatGPT, po weryfikacji obsługi w docelowym
    środowisku.
-   [x] Cotygodniowy job i generowanie na żądanie.
-   [x] Monitoring i powiadomienie o nowej edycji.

**Akceptacja:** oba interfejsy korzystają z tego samego profilu i
historii. (Ukończono pomyślnie)

## Etap 6 -- Zwiastuny i optymalizacja współbieżności

-   [x] Rozszerzenie klienta TMDB o pobieranie wideo zwiastunów (`/movie/{id}/videos`, `/tv/{id}/videos`).
-   [x] Dodanie pól `trailer_url` / `trailer_key` do schematów rekomendacji i metadanych `MediaItem`.
-   [x] Interfejs UI: przycisk zwiastuna i modal z osadzonym odtwarzaczem YouTube (`youtube-nocookie`) bezpośrednio na karcie propozycji (oraz fallback do wyszukiwania).
-   [x] Optymalizacja SQLite: włączenie trybu WAL (`PRAGMA journal_mode=WAL;`) oraz `PRAGMA busy_timeout=5000;` dla bezkolizyjnej pracy 24/7.
-   [x] Zrównoleglenie pobierania kandydatów w TMDB Discovery (`asyncio.gather` z semaforem) w celu skrócenia czasu generowania rekomendacji.
-   [x] Rozszerzenie serwera MCP o narzędzie `get_trailer` oraz uwzględnienie linków `trailer_url` w `get_recommendations`.

**Akceptacja:** Użytkownik może obejrzeć zwiastun prosto z karty przed podjęciem decyzji lub zapytać o zwiastun w MCP (Antigravity / ChatGPT); operacje zapisu i odczytu nie blokują bazy SQLite dzięki WAL. (Ukończono pomyślnie)

## Etap 7 -- Konteneryzacja i wdrożenie na Proxmox

-   [x] Wieloetapowy `Dockerfile` (Python 3.11-slim, instalacja `uv`, użytkownik nieuprzywilejowany `appuser`, healthcheck `/api/health`).
-   [x] Skrypt startowy `scripts/entrypoint.sh` automatycznie wykonujący `alembic upgrade head` przed uruchomieniem `uvicorn` i walidujący uprawnienia zapisu.
-   [x] Konfiguracja `docker-compose.yml` z trwałym montowaniem wolumenu `./data:/app/data`, polityką `restart: unless-stopped` i zarządzaniem zmiennymi `.env`.
-   [x] Dokumentacja i procedura wdrożenia na Proxmox VE (kontener LXC Debian z Dockerem, ochrona bazy w backupach Proxmox/PBS w `docs/deploy-r2d2.md`).
-   [x] Wskazówki konfiguracji Reverse Proxy (Nginx Proxy Manager / Caddy) z HTTPS i wyłączonym buforowaniem pod bezpieczny serwer MCP SSE dla ChatGPT.

**Akceptacja:** Aplikacja działa jako stała, stabilna usługa kontenerowa w środowisku Proxmox, migracje wykonują się bezobsługowo przy starcie, a dane są bezpiecznie persystowane. (Ukończono pomyślnie)

## Etap 8 -- Upublicznienie kodu (GitHub Showcase) i lokalny Mirror (Gitea) [Bez Docker Hub]

-   [x] Audyt bezpieczeństwa repozytorium: weryfikacja `.gitignore`, wykluczenie katalogu `/data/` i lokalnych baz SQLite, audyt braku sekretów w historii 35 commitów, szablony `.env.example`.
-   [x] Zachowanie pełnej, czystej historii w standardzie Conventional Commits.
-   [x] Profesjonalna dokumentacja `README.md` (opis projektu, badges, architektura, instrukcja wdrożenia Docker Compose, konfiguracja Simkl/TMDB/Gemini/MCP).
-   [x] Wyłączenie obsługi zgłoszeń (Issues, PR) oraz włączenie GitHub Discussions dla pytań i wymiany doświadczeń (`CONTRIBUTING.md` / `README.md`).
-   [x] Dodanie pliku licencji (MIT z zastrzeżeniem "as-is").
-   [x] Przygotowanie workflow GitHub Actions CI/CD (automatyczny lint `ruff`, testy `pytest` na `uv` oraz sanity check budowy kontenera Dockera).
-   [x] Konfiguracja własnej instancji Gitea jako automatycznego, pasywnego Pull Mirror z GitHuba (backup off-cloud i źródło deploymentu LAN dla Proxmoxa).
-   [x] Formalna rezygnacja z publikacji na publicznym Docker Hub (kontenery budowane lokalnie na Proxmoxie ze źródeł pobranych z Gitea).

**Akceptacja:** Czyste, bezpieczne repozytorium na GitHubie pełniące rolę publicznego portfolio bez narzutu obsługi społeczności, automatycznie synchronizowany lokalny mirror na Gitea pod Proxmox oraz zautomatyzowane testy CI/CD zakończone sukcesem. (Ukończono pomyślnie)

## Etap 9 -- Wielojęzyczność (i18n: PL/EN) i rozszerzalność dla użytkownika

-   [x] Architektura słowników JSON (`locales/pl.json`, `locales/en.json`) z wbudowanym mechanizmem rozszerzalności (`data/locales/` dla użytkownika).
-   [x] Backendowy serwis `LocaleService` z automatycznym fallbackiem brakujących kluczy.
-   [x] Endpointy API `/api/v1/languages` oraz `/api/v1/languages/{code}`.
-   [x] Dynamiczna lokalizacja UI (HTML/JS/CSS z atrybutami `data-i18n` i selektorem języka w navbarze).
-   [x] Zlokalizowane prompty LLM dla profilu gustu oraz rekomendacji (generowanie `reason`, `positive_factors`, `risks` i `summary` w wybranym języku).
-   [x] Integracja parametru `language` w TMDB API.
-   [x] Rozszerzenie serwera MCP o opcjonalny parametr `language`.

**Akceptacja:** Użytkownik może dynamicznie przełączać język interfejsu (PL/EN), generować rekomendacje w wybranym języku oraz zdefiniować własny język poprzez dodanie pojedynczego pliku JSON. (Ukończono pomyślnie)

## Etap 10 -- Poprawa jakości i puli rekomendacji seriali

Szczegółowy plan techniczny: patrz [docs/plans/plan-seriale-jakosc-rekomendacji.md](docs/plans/plan-seriale-jakosc-rekomendacji.md).

-   [x] Faza 1: Rozszerzenie klienta TMDB (`get_person_tv_credits`) oraz elastyczny resolver złożonych nazw gatunków (`resolve_tmdb_genre_ids`).
-   [x] Faza 2: Zrównoważenie puli ulubionych w bazie (osobne limity dla filmów i seriali) oraz wyszukiwanie seriali twórców (`fetch_creator_shows`) w `DiscoveryService`.
-   [x] Faza 3: Testy jednostkowe z `httpx.MockTransport`, weryfikacja end-to-end, linting `ruff` i ocena jakości proponowanych seriali.

**Akceptacja:** Wygenerowana pula kandydatów serialowych zawiera tytuły odzwierciedlające preferencje użytkownika (kryminał, dramat, twórcy z profilu), eliminując problem sztucznie zaniżonych ocen semantycznych. (Ukończono pomyślnie)

## Etap 11 -- Rekomendacje poszerzające horyzonty: sloty "Zaskocz mnie" (Wildcards)

-   [x] Rozszerzenie modelu bazy danych i migracji Alembic o kolumnę `is_wildcard` w tabeli `recommendations`.
-   [x] Generowanie kandydatów eksploracyjnych w Strategii D (`DiscoveryService`) spoza dominujących gatunków użytkownika.
-   [x] Separacja puli regularnej i eksploracyjnej w `RuleBasedRanker` oraz dywersyfikacji (gwarantowane 9+1 filmów oraz 4+1 seriali).
-   [x] Dedykowane instrukcje dla LLM (analiza przełomowości, atrakcyjności i przekonujące uzasadnienia w języku polskim).
-   [x] Prezentacja w UI: wyróżniający badge `🎲 Zaskocz mnie` na karcie pozycji oraz opcja włączenia/wyłączenia w modalu generowania.
-   [x] Aktualizacja serwera MCP (`is_wildcard` w wynikach, parametr `include_wildcards`).

**Akceptacja:** Każda edycja rekomendacji zawiera dokładnie 1 film i 1 serial wysokiej jakości spoza typowych gatunków profilu, zapobiegając wpadaniu w bańkę rekomendacyjną. (Ukończono pomyślnie)

## Etap 12 -- Niezawodność silnika, odporność LLM i usprawnienia UX (Backlog do realizacji)

-   [ ] **12.1. Jawny wskaźnik trybu awaryjnego (Fallback badge w UI)**:
    - Dodanie flagi `is_fallback` do `RecommendationRunRead` i bazy danych.
    - Wizualna informacja w interfejsie (`⚡ Tryb awaryjny – rekomendacje wygenerowane na podstawie rankera lokalnego`), gdy serwery Gemini były niedostępne.
-   [ ] **12.2. Podział oceny kandydatów na mniejsze paczki (Batching LLM)**:
    - Ewaluacja kandydatów w mniejszych partiach (np. po 10-12 pozycji zamiast 25 naraz).
    - Zmniejszenie obciążenia pojedynczych requestów i eliminacja ryzyka zrzucenia połączenia (503) przez upstream Google.
-   [ ] **12.3. Automatyczny test spójności bazy danych (`alembic check` w pytest)**:
    - Test weryfikujący zgodność modeli SQLAlchemy z bieżącymi migracjami Alembic.
    - Fail-fast w CI w razie braku wygenerowania lub zastosowania migracji.
-   [ ] **12.4. Asynchroniczne generowanie edycji ze statusem postępu (Background Jobs)**:
    - Refaktoryzacja `POST /api/recommendation-runs` na zadanie w tle (odpowiedź `202 Accepted`).
    - Pasek postępu i polling statusu w UI (np. *„1/3 Pobieranie kandydatów... 2/3 Analiza AI... 3/3 Zróżnicowanie listy...”*).

## Przyszłe rozszerzenia (Future Backlog)

-   Powiadomienia Pushover / Telegram o wygenerowaniu nowej edycji przez scheduler.
-   Embeddingi i analiza wektorowa podobieństwa pozycji.
-   Analiza zmian i ewolucji gustu użytkownika w czasie.
-   Dodatkowe źródła metadanych i alternatywni dostawcy LLM.
