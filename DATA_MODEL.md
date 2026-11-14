# Data Model

SQLite; identyfikatory zewnętrzne przechowuj osobno od kluczy
wewnętrznych. Daty w UTC/ISO 8601.

## Tabele

### `media_items`

-   `id` -- PK
-   `media_type` -- `movie` / `show`
-   `title`, `year`
-   `tmdb_id`, `simkl_id`, `imdb_id` -- nullable, indeksowane
-   `metadata_json` -- opcjonalne, ograniczone metadane
-   `created_at`, `updated_at`

Unikalność: typ + dostępny identyfikator źródłowy; nie zakładaj, że
tytuł jest unikalny.

### `watch_history`

-   `id` -- PK
-   `media_item_id` -- FK
-   `status`, `watched_at`, `user_rating`
-   `source_updated_at`, `synced_at`

### `taste_profiles`

-   `id` -- PK
-   `version` -- unikalna wersja
-   `profile_json` -- preferencje, antypreferencje, notatki
-   `created_at`, `based_on_sync_at`
-   `active` -- bool

Profil JSON powinien rozdzielać wagę preferencji od pewności modelu.

### `recommendation_runs`

-   `id` -- PK
-   `created_at`, `status`
-   `profile_version`
-   `model_provider`, `model_name`
-   `parameters_json`, `summary`

### `recommendations`

-   `id` -- PK
-   `run_id` -- FK
-   `media_item_id` -- FK
-   `match_score`, `confidence`
-   `reason`, `positive_factors_json`, `risks_json`
-   `status` -- `pending` / `accepted` / `rejected` / `seen` / `added` /
    `error`
-   `created_at`

Unikalność: `run_id + media_item_id`.

### `user_decisions`

-   `id` -- PK
-   `recommendation_id` -- FK
-   `decision` -- `accept` / `reject` / `seen` / `later`
-   `created_at`, `note`

### `sync_state`

-   `provider` -- PK
-   `last_success_at`, `cursor_or_activity_state`
-   `status`, `error_summary`

### `app_settings`

-   `key` -- PK
-   `value_json`

## Reguły

-   Nie nadpisuj lokalnych decyzji historią Simkl.
-   Zachowuj wersje profilu i parametry każdego przebiegu rekomendacji.
-   Nie usuwaj odrzuconych propozycji; wykorzystuj je do deduplikacji i
    analizy.
-   Tokeny OAuth przechowuj w bezpiecznym magazynie/zaszyfrowanej
    konfiguracji, nie w tabelach aplikacyjnych w postaci jawnej.
