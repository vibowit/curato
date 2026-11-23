# Plan implementacji: Poprawa jakości i puli rekomendacji seriali

## Cel

Wyeliminowanie problemu niskich ocen semantycznych seriali (maks. 45–48% w obecnych propozycjach) poprzez usunięcie wąskich gardeł w procesie pozyskiwania kandydatów z TMDB:
1. Wyszukiwanie seriali powiązanych z ulubionymi twórcami i showrunnerami (*Strategy C*).
2. Elastyczne mapowanie złożonych gatunków profilu (np. `Action/Thriller`, `History/War`) na właściwe identyfikatory TMDB TV (*Strategy B*).
3. Zrównoważenie puli ulubionych pozycji (*Strategy A*), aby filmy nie wypierały seriali, a rekomendacje bazowały na szerokim zestawie ulubionych seriali użytkownika.

---

## Architektura rozwiązania

```mermaid
flowchart TD
    subgraph Faza 1: Klient TMDB i Mapowanie Gatunków
        A1[TMDBClient: get_person_tv_credits] --> A2[Genre Resolver: rozbijanie Action/Thriller itp.]
        A2 --> A3[Testy jednostkowe TMDBClient i mapowania]
    end

    subgraph Faza 2: DiscoveryService - Twórcy i Zrównoważone Ulubione
        B1[Discovery: dedykowana pula ulubionych seriali] --> B2[Discovery: fetch_creator_shows dla twórców]
        B2 --> B3[Discovery: wykorzystanie Genre Resolvera]
        B3 --> B4[Testy jednostkowe DiscoveryService z MockTransport]
    end

    subgraph Faza 3: Weryfikacja i Testy Integracyjne
        C1[Testy regresyjne: pytest] --> C2[Linter i formatowanie: ruff]
        C2 --> C3[Weryfikacja jakości kandydatów serialowych]
    end

    Faza 1 --> Faza 2
    Faza 2 --> Faza 3
```

---

## Faza 1: Rozszerzenie klienta TMDB i elastyczny resolver gatunków

### Problem
- `TMDBClient` posiada wyłącznie `get_person_movie_credits`, brak metody na pobranie dorobku serialowego twórcy (`/person/{person_id}/tv_credits`).
- TMDB rozróżnia inne identyfikatory gatunkowe dla filmów i dla seriali. Profil gustu generuje nazwy złożone (np. `Action/Thriller`, `History/War`), które przy sztywnym porównaniu `if g_name in TMDB_TV_GENRES:` nie dopasowują się do żadnego identyfikatora i są ignorowane.

### Zakres zmian

#### 1. `app/integrations/tmdb.py`
- Dodanie metody `get_person_tv_credits(self, person_id: int) -> Dict[str, Any]` odpytującej endpoint `/person/{person_id}/tv_credits`.
- Rozszerzenie słowników lub dodanie funkcji pomocniczej `resolve_tmdb_genre_ids(genre_name: str, media_type: str) -> List[int]`:
  - Normalizacja tekstu (lowercase, usunięcie zbędnych znaków).
  - Rozbijanie separatorów (`/`, `&`, `,`, `-`, np. `Action/Thriller` -> tokeny `action`, `thriller`).
  - Inteligentne mapowanie tokenów na identyfikatory TMDB:
    - Dla seriali (`show`):
      - `action` / `adventure` -> `10759` (Action & Adventure)
      - `thriller` / `mystery` -> `9648` (Mystery) lub `80` (Crime)
      - `war` / `history` / `politics` -> `10768` (War & Politics)
      - `sci-fi` / `fantasy` -> `10765` (Sci-Fi & Fantasy)
      - `crime` -> `80`
      - `drama` -> `18`
      - `western` -> `37`
    - Dla filmów (`movie`):
      - `action` -> `28`, `adventure` -> `12`, `thriller` -> `53`, `crime` -> `80`, `drama` -> `18`, `history` -> `36`, `war` -> `10752`, `sci-fi` -> `878`, `mystery` -> `9648`.

#### 2. `tests/test_tmdb_client.py`
- Testy dla `get_person_tv_credits` z mockowaniem `httpx.MockTransport`.
- Testy dla resolvera gatunków (obsługa `Action/Thriller`, `History/War`, `Crime`, pojedynczych i złożonych nazw).

---

## Faza 2: Zrównoważenie puli ulubionych i wyszukiwanie seriali twórców w `DiscoveryService`

### Problem
- W Strategii A (`similar_to_favorites`) pobierane jest ogólne top 10 ulubionych. Z powodu przewagi liczbowej filmów z oceną 10.0 w bazie, do puli trafiają niemal wyłącznie filmy i tylko 2 seriale (*Breaking Bad* i *Game of Thrones*). To z *Game of Thrones* TMDB podsyła tytuły fantasy, które LLM potem słusznie odrzuca ze względu na preferencję surowego realizmu.
- W Strategii C (`directors_or_creators`) odpytywano wyłącznie o filmy (`fetch_creator_movies`). Seriale takich twórców jak Taylor Sheridan (*Mayor of Kingstown*, *Tulsa King*, *Lioness*, *1883*) czy David Fincher (*Mindhunter*, *House of Cards*) były całkowicie pomijane.

### Zakres zmian

#### 1. `app/services/discovery.py`
- **Zrównoważenie ulubionych w bazie:**
  - Zmiana `get_favorites_from_db`: zamiast jednej wspólnej listy, metoda pobiera niezależnie ulubione filmy oraz ulubione seriale (np. do 5 najlepszych filmów ORAZ do 5 najlepszych seriali z oceną $\ge 7.5$ lub statusem `completed`).
  - Dzięki temu w zapytaniach do TMDB pojawi się zróżnicowany zestaw inspiracji (np. *The Wire*, *The Sopranos*, *Chernobyl*, *Gomorrah*, *Breaking Bad*, *Vikings*), a nie tylko pozycje fantasy z *Game of Thrones*.
- **Wyszukiwanie seriali twórców (`fetch_creator_shows`):**
  - Dla każdego twórcy z profilu gustu (`profile.directors_or_creators[:4]`), obok `fetch_creator_movies`, uruchomienie `fetch_creator_shows`.
  - Wykorzystanie `get_person_tv_credits`: weryfikacja ról w sekcji `crew` (np. Creator, Director, Writer, Executive Producer) z filtrowaniem minimalnej liczby głosów (`vote_count >= 20`) i pomijaniem wykluczonych gatunków.
- **Wykorzystanie elastycznego resolvera gatunków:**
  - W Strategii B (`profile_genres`), zamiast prostego słownika, użycie `resolve_tmdb_genre_ids` dla filmów i seriali, eliminując problem pomijania `Action/Thriller` i `History/War`.

#### 2. `tests/test_discovery_service.py`
- Dedykowany plik testowy dla `DiscoveryService`:
  - Test zrównoważonego pobierania ulubionych (filmy vs seriale).
  - Test wyszukiwania seriali twórców (`fetch_creator_shows`).
  - Test odkrywania kandydatów na podstawie złożonych gatunków.
  - Wszystkie zapytania HTTP zamockowane za pomocą `httpx.MockTransport`.

---

## Faza 3: Weryfikacja end-to-end, testy integracyjne i ewaluacja jakości

### Zakres zmian
1. **Weryfikacja całościowego pipeline'u rekomendacji:**
   - Sprawdzenie, jak `RuleBasedRanker` i `RecommendationService` współpracują z nowo pozyskanymi kandydatami serialowymi.
   - Uruchomienie istniejących testów w `tests/test_recommendation_services.py` i `tests/test_recommendation_api.py`.
2. **Uruchomienie lintera i formatera:**
   - Wykonanie `ruff check .` i `ruff format --check .`.
3. **Weryfikacja działania na rzeczywistych danych (skrypt dry-run):**
   - Sprawdzenie w kontrolowany sposób (bez tworzenia niechcianych rekordów w bazie lub na kopii testowej), jakie seriale trafiają teraz do puli kandydatów dla profilu użytkownika.

---

## Verification Plan

### Testy automatyczne
```bash
# 1. Nowe i istniejące testy TMDB i Discovery
.venv/bin/pytest tests/test_tmdb_client.py tests/test_discovery_service.py tests/test_recommendation_services.py -v

# 2. Pełny zestaw testów repozytorium
.venv/bin/pytest

# 3. Sprawdzenie lintera
.venv/bin/ruff check .
```

### Weryfikacja manualna / logów
- Sprawdzenie struktury wygenerowanych kandydatów serialowych (czy w puli pojawiają się seriale twórców z profilu oraz seriale z gatunków akcji/thrillera/politycznych z wysokimi ocenami).
