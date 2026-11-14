---
id: "movie-recommend"
title: "System Rekomendacji Filmów i Seriali (Simkl + Gemini/OpenAI + FastAPI + MCP)"
status: in_progress
priority: P1
category: dev
created: "2026-11-06"
updated: "2026-11-14"
next_action: "Zrealizować Etap 0 (Fundament): struktura katalogów w app/, konfiguracja FastAPI, modele bazy SQLite wg DATA_MODEL.md oraz Pydantic Settings"
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
- [ ] Stabilny szkielet aplikacji w `FastAPI` z bazą `SQLite` i migracjami.
- [ ] Integracja z Simkl: autoryzacja, synchronizacja biblioteki/ocen/Plan to Watch, idempotentny zapis wyłącznie zaakceptowanych pozycji.
- [ ] Wersjonowany profil gustu użytkownika z możliwością ręcznej korekty.
- [ ] Silnik rekomendacji integrujący TMDB i LLM (10 filmów, 5 seriali na edycję) z uzasadnieniami i bez duplikatów.
- [ ] Prosty interfejs użytkownika do przeglądu i zatwierdzania/odrzucania propozycji.
- [ ] Serwer MCP (STDIO dla Antigravity, HTTPS dla ChatGPT) udostępniający te same serwisy domenowe.
- [ ] Testy automatyczne (pokrycie kluczowych modułów > 80%, testy mockujące Simkl/TMDB/LLM).
- [ ] Dokumentacja uruchomieniowa i szablon `.env.example`.

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
  - Wszystkie testy jednostkowe przechodzą (6/6 OK). Potwierdzono gwarancję zera operacji zapisu do Simkl.
- **Kluczowe moduły**:
  - `scripts/poc_taste_engine.py` — samodzielny skrypt badawczy PoC
  - `scripts/get_simkl_token.py` — asystent autoryzacji OAuth 2.0 Simkl Device Flow
  - `app/api/` — endpointy REST (FastAPI)
  - `app/integrations/` — adaptery do Simkl, TMDB, LLM
  - `app/services/` — logika domenowa (sync, profil gustu, ranking, rekomendacje)
  - `app/mcp/` — cienka warstwa adaptera MCP
  - `app/models/` — modele bazy i schematy domenowe
  - `tests/` — testy jednostkowe i integracyjne
  - `data/` — lokalna baza SQLite i eksporty badawcze

## Najbliższy Krok (Next Action)

> Zrealizować Etap 0 (Fundament): struktura katalogów w app/, konfiguracja FastAPI, modele bazy SQLite wg DATA_MODEL.md oraz Pydantic Settings.

## Blokady (Blockers)

Brak. Etap PoC pomyślnie zakończony, środowisko i autoryzacje Simkl/Gemini działają.

## Backlog Zadań

### Etap PoC: Simkl Taste Engine (walidacja koncepcji)
- [x] Przygotowanie szablonu `.env.example` (zmienne dla Simkl i Gemini API) oraz konfiguracji `pyproject.toml` (`uv`)
- [x] Implementacja skryptu `scripts/poc_taste_engine.py` do pobrania historii Simkl
- [x] Generowanie profilu gustu i 10 filmów + 5 seriali przez Gemini
- [x] Ewaluacja jakości wygenerowanych rekomendacji przez użytkownika

### Etap 0: Fundament
- [ ] Inicjalizacja repozytorium i struktury `app/`
- [ ] FastAPI, SQLite i migracje schematu bazy wg `DATA_MODEL.md`
- [ ] Logowanie, obsługa błędów, konfiguracja sekretów z walidacją Pydantic Settings
- [ ] Konfiguracja testów `pytest` i reguł `ruff`

### Etap 1: Simkl
- [ ] Klient API Simkl i obsługa uwierzytelniania
- [ ] Pobieranie historii, ocen i listy Plan to Watch
- [ ] Przyrostowa synchronizacja do SQLite
- [ ] Idempotentny zapis zaakceptowanych pozycji z testami

### Etap 2: Profil gustu
- [ ] Serwis analizy historii i preferencji
- [ ] Generowanie i wersjonowanie profilu JSON (wagi, confidence)
- [ ] Możliwość ręcznej korekty profilu

### Etap 3: Rekomendacje
- [ ] Integracja z TMDB (wyszukiwanie kandydatów, metadane)
- [ ] Filtry anty-rekomendacji (obejrzane, Plan to Watch, odrzucone)
- [ ] Ranking regułowy + ocena semantyczna LLM
- [ ] Dywersyfikacja wyników i rejestracja przebiegu w bazie

### Etap 4: Panel i zatwierdzanie
- [ ] Minimalny UI do przeglądu propozycji
- [ ] Rejestracja decyzji użytkownika (`accept`, `reject`, `seen`, `later`)
- [ ] Idempotentne, kontrolowane dodawanie zaakceptowanych pozycji do Simkl

### Etap 5: MCP i harmonogram
- [ ] Narzędzia MCP STDIO dla Antigravity
- [ ] MCP HTTPS/Streamable dla ChatGPT
- [ ] Scheduler dla cotygodniowego generowania propozycji

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
