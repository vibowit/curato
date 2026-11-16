# API Contracts

Kontrakty są propozycją dla MVP. Szczegóły endpointów zewnętrznych
należy zweryfikować w aktualnej dokumentacji Simkl i TMDB przed
implementacją.

## REST API (frontend)

### `GET /api/health`

Zwraca stan aplikacji bez ujawniania sekretów.

### `GET /api/profile`

Zwraca aktywny profil gustu i jego wersję.

### `POST /api/sync/simkl`

Uruchamia synchronizację. Odpowiedź: status, liczba
nowych/zaktualizowanych pozycji, czas ostatniej synchronizacji.

### `POST /api/recommendation-runs`

Generuje nową edycję. Request:

``` json
{"movie_limit": 10, "show_limit": 5, "mode": "weekly"}
```

Response: `run_id`, status.

### `GET /api/recommendation-runs/{run_id}`

Zwraca metadane przebiegu i rekomendacje.

### `POST /api/recommendations/decisions`

Zapisuje decyzje użytkownika. Request:

``` json
{"decisions":[{"recommendation_id":123,"decision":"accept"}]}
```

Dozwolone decyzje: `accept`, `reject`, `seen`, `later`.

### `POST /api/recommendations/approve`

Dodaje wyłącznie wcześniej zaakceptowane rekomendacje do Simkl. Request:

``` json
{"recommendation_ids":[123,124]}
```

Operacja musi być idempotentna i zwrócić status każdej pozycji.

## MCP tools

-   `get_taste_profile()` -- aktywny profil.
-   `get_library_stats()` -- podsumowanie biblioteki i daty
    synchronizacji.
-   `sync_simkl()` -- jawnie uruchamia synchronizację.
-   `generate_recommendations(movie_limit?, show_limit?)` -- tworzy
    przebieg.
-   `get_recommendations(run_id?)` -- pobiera listę do przeglądu.
-   `record_decision(recommendation_id, decision, note?)` -- zapisuje
    decyzję.
-   `approve_recommendations(recommendation_ids)` -- zapisuje wcześniej
    zaakceptowane pozycje do Simkl.
-   `get_recommendation_history(limit?)` -- historia przebiegów i
    decyzji.

MCP nie powinien udostępniać narzędzia pozwalającego ominąć akceptację.

## Kontrakty i błędy

-   Waliduj wszystkie identyfikatory i typy.
-   Używaj stabilnych kodów błędów: `AUTH_REQUIRED`, `RATE_LIMITED`,
    `UPSTREAM_ERROR`, `NOT_FOUND`, `INVALID_STATE`.
-   Zapisuj correlation/request ID.
-   Nie zwracaj tokenów ani sekretów.
-   Operacje zapisu powinny obsługiwać ponowienie bez duplikowania
    pozycji.
