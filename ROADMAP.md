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

-   [ ] Analiza historii i ocen.
-   [ ] Pierwszy profil JSON z wagami i confidence.
-   [ ] Wersjonowanie i ręczna korekta profilu.

**Akceptacja:** profil ma uzasadnienie i można odtworzyć, z jakich
danych powstał.

## Etap 3 -- rekomendacje

-   [ ] Integracja TMDB.
-   [ ] Generowanie i normalizacja kandydatów.
-   [ ] Filtry obejrzanych, Plan to Watch i odrzuconych.
-   [ ] Ranking regułowy i ocena LLM.
-   [ ] Dywersyfikacja i zapis przebiegów.

**Akceptacja:** system tworzy listę 10 filmów i 5 seriali bez duplikatów
i z uzasadnieniami.

## Etap 4 -- panel i zatwierdzanie

-   [ ] Lista rekomendacji.
-   [ ] Decyzje: zaakceptuj, odrzuć, już widziałem, później.
-   [ ] Zbiorcze dodawanie zaakceptowanych do Simkl.
-   [ ] Historia przebiegów i decyzji.

**Akceptacja:** pełny przepływ od listy do Plan to Watch działa bez
automatycznego zapisu.

## Etap 5 -- MCP i harmonogram

-   [ ] MCP STDIO dla Antigravity.
-   [ ] MCP HTTPS dla ChatGPT, po weryfikacji obsługi w docelowym
    środowisku.
-   [ ] Cotygodniowy job i generowanie na żądanie.
-   [ ] Monitoring i powiadomienie o nowej edycji.

**Akceptacja:** oba interfejsy korzystają z tego samego profilu i
historii.

## Po MVP

Embeddingi, bardziej zaawansowana personalizacja, analiza zmian gustu,
powiadomienia Pushover i dodatkowe źródła metadanych.
