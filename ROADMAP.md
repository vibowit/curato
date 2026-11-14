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

## Po MVP

Embeddingi, bardziej zaawansowana personalizacja, analiza zmian gustu,
powiadomienia Pushover i dodatkowe źródła metadanych.
