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

-   [ ] Wieloetapowy `Dockerfile` (Python 3.11-slim, użytkownik nieuprzywilejowany `appuser`, healthcheck `/api/health`).
-   [ ] Skrypt startowy `entrypoint.sh` automatycznie wykonujący `alembic upgrade head` przed uruchomieniem `uvicorn`.
-   [ ] Konfiguracja `docker-compose.yml` z trwałym montowaniem wolumenu `./data:/app/data`, polityką `restart: unless-stopped` i zarządzaniem zmiennymi `.env`.
-   [ ] Dokumentacja i procedura wdrożenia na Proxmox VE (kontener LXC Debian z Dockerem, ochrona bazy w backupach Proxmox/PBS).
-   [ ] Wskazówki konfiguracji Reverse Proxy (Nginx Proxy Manager / Caddy / Cloudflare Tunnel) z HTTPS pod bezpieczny serwer MCP SSE dla ChatGPT.

**Akceptacja:** Aplikacja działa jako stała, stabilna usługa kontenerowa w środowisku Proxmox, migracje wykonują się bezobsługowo przy starcie, a dane są bezpiecznie persystowane.

## Etap 8 -- Upublicznienie kodu (GitHub Showcase) i lokalny Mirror (Gitea) [Bez Docker Hub]

-   [ ] Audyt bezpieczeństwa repozytorium: weryfikacja `.gitignore`, wykluczenie katalogu `/data/` i lokalnych baz SQLite, audyt sekretów w historii git (`gitleaks`), szablony `.env.example`.
-   [ ] Przygotowanie czystego commita startowego (`orphan branch`) dla publicznego repozytorium na GitHubie.
-   [ ] Profesjonalna dokumentacja `README.md` (opis projektu, badges, architektura, instrukcja wdrożenia Docker Compose na Proxmox, konfiguracja Simkl/TMDB/Gemini/MCP).
-   [ ] Wyłączenie obsługi zgłoszeń (Issues, Discussions, PR) w repozytorium GitHub oraz dodanie noty w `CONTRIBUTING.md` / `README.md` o charakterze projektu (bespoke / showcase portfolio).
-   [ ] Dodanie pliku licencji (np. MIT z zastrzeżeniem "as-is").
-   [ ] Przygotowanie workflow GitHub Actions CI/CD (automatyczny lint `ruff` i testy `pytest` przy commitach do `main`).
-   [ ] Konfiguracja własnej instancji Gitea jako automatycznego, pasywnego Pull Mirror z GitHuba (backup off-cloud i źródło deploymentu LAN dla Proxmoxa).
-   [ ] Formalna rezygnacja z publikacji na publicznym Docker Hub (kontenery budowane lokalnie na Proxmoxie ze źródeł pobranych z Gitea).

**Akceptacja:** Czyste, bezpieczne repozytorium na GitHubie pełniące rolę publicznego portfolio bez narzutu obsługi społeczności, automatycznie synchronizowany lokalny mirror na Gitea pod Proxmox oraz zautomatyzowane testy CI/CD.

## Przyszłe rozszerzenia (Future Backlog)

-   Powiadomienia Pushover / Telegram o wygenerowaniu nowej edycji przez scheduler.
-   Embeddingi i analiza wektorowa podobieństwa pozycji.
-   Analiza zmian i ewolucji gustu użytkownika w czasie.
-   Dodatkowe źródła metadanych i alternatywni dostawcy LLM.
