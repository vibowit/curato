# Architecture

## Zasada

Jeden niezależny backend i jedna baza. Antigravity oraz ChatGPT są
wymiennymi klientami przez MCP; nie zawierają własnej logiki domenowej.

## Komponenty

-   **FastAPI** -- REST API dla frontendu i logika aplikacji.
-   **SQLite** -- historia synchronizacji, profil, rekomendacje i
    decyzje.
-   **Simkl adapter** -- OAuth, odczyt biblioteki/list, zapis
    zatwierdzonych tytułów.
-   **TMDB adapter** -- wyszukiwanie kandydatów i metadane.
-   **LLM adapter** -- wspólny interfejs do Gemini i OpenAI.
-   **Recommendation service** -- filtracja, ranking, dywersyfikacja.
-   **MCP server** -- cienka warstwa narzędzi wywołująca te same
    serwisy.
-   **Frontend** -- prosta lista rekomendacji i ekran zatwierdzania.
-   **Scheduler** -- cotygodniowe uruchomienie; rekomendacje bazują na
    lokalnej kopii danych.

## Przepływ

Simkl/TMDB → adapters → services → SQLite → REST/MCP → użytkownik →
jawna akceptacja → Simkl.

## Proponowana struktura

``` text
app/
  api/
  core/
  integrations/
    simkl.py
    tmdb.py
    llm/
  services/
    sync.py
    taste.py
    discovery.py
    ranking.py
    recommendations.py
  mcp/
  models/
  main.py
frontend/
tests/
data/
```

## Uruchamianie i integracje

-   Lokalnie: backend i MCP STDIO dla Antigravity.
-   Zdalnie: MCP przez HTTPS/Streamable HTTP dla ChatGPT, jeśli wybrany
    plan i konfiguracja ChatGPT to obsługują.
-   Scheduler uruchamia cotygodniowy job niezależnie od sesji agenta.
-   Sekrety przechowuj poza repozytorium; baza i tokeny nie mogą być
    publicznie dostępne.

## Bezpieczeństwo i niezawodność

-   OAuth z PKCE, minimalne wymagane uprawnienia i bezpieczne
    przechowywanie tokenów.
-   Nie loguj tokenów ani pełnych danych uwierzytelniających.
-   Zapis do Simkl tylko po jawnej akceptacji; operacje idempotentne.
-   Timeouty, retry z backoffem i obsługa limitów API.
-   Zachowuj surowe odpowiedzi tylko wtedy, gdy są potrzebne do
    diagnostyki; ogranicz dane osobowe.
-   Testy adapterów z mockami oraz testy integracyjne na koncie
    testowym.

## Decyzje do potwierdzenia podczas implementacji

Sprawdź aktualne wersje endpointów, OAuth flow, zakresy, limity i
formaty identyfikatorów Simkl. Zweryfikuj dostępność MCP przez HTTPS w
docelowym ChatGPT. Nie zakładaj, że wszystkie przykłady API z
wcześniejszych wersji nadal działają.
