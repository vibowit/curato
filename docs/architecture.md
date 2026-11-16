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
-   **LLM adapter** -- protokół `LLMProvider` i moduł adaptera z zaimplementowanym klientem Gemini (`GeminiLLMClient`), przygotowany pod kolejnych dostawców (np. OpenAI).
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

-   OAuth z PKCE oraz wsparcie dla Device/PIN flow dla CLI/skryptów.
-   Bezpieczne przechowywanie tokenów w `.env` i brak logowania sekretów.
-   Limity Simkl API:
    -   Maksymalnie 500 żądań dziennie (daily rate limit).
    -   1 żądanie POST / sekundę.
    -   10 żądań GET / sekundę.
-   Zapis do Simkl tylko po jawnej akceptacji; operacje idempotentne.
-   Timeouty, retry z backoffem i kolejkowanie z poszanowaniem limitów.
-   Zachowuj surowe odpowiedzi tylko wtedy, gdy są potrzebne do
    diagnostyki; ogranicz dane osobowe.
-   Testy adapterów z mockami oraz testy integracyjne na koncie
    testowym.

## Strategia repozytoriów, backupu i rejestrów

-   **GitHub (Primary / Single Source of Truth)**:
    -   Publiczne repozytorium służące jako showcase inżynierski i portfolio.
    -   Brak narzutu społeczności: sekcje Issues, Discussions i Pull Requests są wyłączone lub zablokowane.
    -   Darmowe GitHub Actions do automatycznych testów (`pytest`) i lintingu (`ruff`).
-   **Gitea (Pasywny Mirror / LAN Deployment / Off-cloud Backup)**:
    -   Własna instancja Gitea w homelabie skonfigurowana jako automatyczny Pull Mirror z GitHuba.
    -   Nigdy nie wykonuje się bezpośrednich pushów do Gitea ze stacji roboczej (ochrona przed rozjechaniem gałęzi).
    -   Proxmox (LXC/VM) pobiera kod i buduje kontenery bezpośrednio w sieci LAN z Gitea (odporność na brak łącza internetowego).
-   **Rezygnacja z Docker Hub**:
    -   Brak publikacji na publicznym Docker Hub ze względów bezpieczeństwa, specyfiki pojedynczego użytkownika (bespoke) oraz minimalizacji narzutu utrzymania.
    -   Kontenery budowane lokalnie na serwerze Proxmox (`docker compose build`) z wykorzystaniem cache i `uv`.

## Decyzje do potwierdzenia podczas implementacji

Sprawdź aktualne wersje endpointów, OAuth flow, zakresy, limity i
formaty identyfikatorów Simkl. Zweryfikuj dostępność MCP przez HTTPS w
docelowym ChatGPT. Nie zakładaj, że wszystkie przykłady API z
wcześniejszych wersji nadal działają.
