# System Rekomendacji Filmów i Seriali (Movie & Show Recommender)

Prywatny system rekomendacji filmów i seriali oparty na Twojej historii i ocenach z **Simkl**, dynamicznym wersjonowaniu profilu gustu oraz analizie **LLM (Gemini/OpenAI)** i bazie **TMDB**.

System udostępnia:
- **Webowy panel użytkownika (SPA)** serwowany przez FastAPI (`http://localhost:8000/`) do przeglądu propozycji, podejmowania decyzji (`Zaakceptuj`, `Odrzuć`, `Już widziałem`, `Później`) i bezpiecznego dodawania pozycji do Simkl Plan to Watch.
- **REST API + Swagger UI** (`http://localhost:8000/docs`).
- **Serwer Model Context Protocol (MCP)**:
  - **STDIO**: dla lokalnych asystentów AI (Antigravity IDE / CLI, Claude Desktop, Cursor).
  - **HTTPS / SSE**: dla ChatGPT (Custom Actions) i zdalnych klientów.
- **Harmonogram w tle**: cotygodniowa synchronizacja i automatyczne generowanie świeżej edycji.

---

## 1. Wymagania i instalacja

Projekt korzysta z Pythona 3.11+ oraz menedżera `uv` (lub standardowego `pip`).

```bash
# 1. Klonowanie i wejście do katalogu
git clone <repo_url>
cd movie-recommend

# 2. Utworzenie środowiska wirtualnego i instalacja zależności
uv sync
# lub: python -m venv .venv && source .venv/bin/activate && pip install -e .
```

---

## 2. Konfiguracja zmiennych środowiskowych

Skopiuj plik `.env.example` do `.env` i uzupełnij klucze API:

```bash
cp .env.example .env
```

Wymagane klucze w `.env`:
- `SIMKL_CLIENT_ID` i `SIMKL_CLIENT_SECRET`: z [Simkl Developer Portal](https://simkl.com/settings/developer/).
- `SIMKL_USER_TOKEN`: token autoryzacyjny użytkownika (można wygenerować asystentem `python scripts/get_simkl_token.py`).
- `TMDB_API_KEY`: klucz API z [The Movie Database](https://www.themoviedb.org/settings/api).
- `GEMINI_API_KEY`: klucz API z [Google AI Studio](https://aistudio.google.com/).
- Opcjonalnie: `MCP_API_KEY` (ochrona transportu SSE dla zdalnych asystentów), `SCHEDULER_ENABLED=true` (włączenie cotygodniowego joba w tle).

---

## 3. Inicjalizacja bazy danych i uruchomienie

```bash
# 1. Migracje bazy SQLite (Alembic)
.venv/bin/alembic upgrade head

# 2. Uruchomienie serwera FastAPI
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Po uruchomieniu przejdź do:
- **Panel przeglądu i decyzji:** [http://localhost:8000/](http://localhost:8000/)
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Status aplikacji:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 4. Konfiguracja serwera MCP

### A. Antigravity IDE / CLI (STDIO)
W pliku konfiguracyjnym Antigravity (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "movie-recommender": {
      "command": "/pełna/ścieżka/do/movie-recommend/.venv/bin/python",
      "args": ["-m", "app.mcp.cli"],
      "cwd": "/pełna/ścieżka/do/movie-recommend"
    }
  }
}
```

Dostępne narzędzia MCP:
- `get_taste_profile()` – pobiera aktualny profil gustu (gatunki, motywy, reżyserzy, antypreferencje).
- `get_library_stats()` – statystyki lokalnej bazy (filmy, seriale, oceny, czas synchronizacji).
- `sync_simkl(full_sync)` – uruchamia synchronizację z Simkl.
- `generate_recommendations(movie_limit, show_limit)` – generuje nową edycję.
- `get_recommendations(run_id)` – pobiera listę propozycji z uzasadnieniami.
- `record_decision(recommendation_id, decision, note)` – rejestruje decyzję użytkownika (`accept`, `reject`, `seen`, `later`).
- `approve_recommendations(recommendation_ids)` – **bezpieczny, idempotentny zapis wyłącznie zaakceptowanych pozycji** do Simkl Plan to Watch.
- `get_recommendation_history(limit)` – historia przebiegów i edycji.

### B. ChatGPT (Streamable HTTP / SSE)
- **Endpoint SSE:** `https://twoja-domena.pl/mcp/sse`
- **Wiadomości:** `https://twoja-domena.pl/mcp/messages/`
- **Autoryzacja:** Bearer Token (`MCP_API_KEY`)

---

## 5. Testy automatyczne i jakość kodu

```bash
# Uruchomienie pełnego pakietu 103 testów
.venv/bin/pytest

# Weryfikacja formatowania i lintera
.venv/bin/ruff check app tests
```
