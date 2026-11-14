# Product: Personal Movie Recommender

## Cel

Osobisty system rekomendacji filmów i seriali oparty na historii Simkl i
profilu gustu użytkownika. System proponuje tytuły; użytkownik zawsze
sam decyduje, co dodać do Simkl.

## Ustalone założenia

-   Dwa interfejsy LLM: Antigravity/Gemini oraz ChatGPT/GPT.
-   Jeden wspólny backend, baza danych i profil gustu.
-   Nowa edycja rekomendacji co tydzień oraz generowanie na żądanie.
-   Zatwierdzanie ręczne; brak automatycznego dodawania do listy.
-   Dostępność w serwisach streamingowych nie jest filtrem.
-   Simkl jest źródłem historii i miejscem zapisu zaakceptowanych
    pozycji.
-   Stremio korzysta z istniejącej integracji z listą Simkl.

## Użytkownik i główny przepływ

1.  System synchronizuje historię, oceny i listę Plan to Watch z Simkl.
2.  Aktualizuje profil gustu.
3.  Pobiera kandydatów z katalogu TMDB i filtruje pozycje już znane.
4.  Ocenia i porządkuje kandydatów z pomocą reguł oraz LLM.
5.  Publikuje listę do przeglądu.
6.  Użytkownik zatwierdza wybrane tytuły.
7.  System dodaje zatwierdzone pozycje do Simkl.

## MVP

-   Integracja Simkl: autoryzacja, odczyt biblioteki/list, zapis
    zaakceptowanych pozycji.
-   Integracja TMDB do wyszukiwania metadanych i kandydatów.
-   Lokalna baza i wersjonowany profil gustu.
-   Ranking i lista rekomendacji: domyślnie 10 filmów i 5 seriali.
-   Minimalny interfejs do przeglądania, akceptacji i odrzucania.
-   MCP dla Antigravity i ChatGPT.
-   Cotygodniowe uruchomienie i generowanie na żądanie.

## Kolejne rozszerzenia (Next Milestones)

-   Podgląd oficjalnych zwiastunów (trailers z TMDB / YouTube) bezpośrednio w panelu rekomendacji przed podjęciem decyzji.
-   Konteneryzacja i wdrożenie jako stała, bezobsługowa usługa domowa w środowisku Proxmox VE (Docker Compose, montowanie wolumenu danych, restart-policy).
-   Przygotowanie projektu do upublicznienia na GitHubie (jako showcase inżynierski bez obsługi zgłoszeń) oraz konfiguracja pasywnego mirrora Gitea pod Proxmox; rezygnacja z publikacji na Docker Hub na rzecz lokalnego buildu.

## Poza zakresem MVP

Dostępność streamingowa, własny katalog filmów, trenowanie ML,
embeddingi, wieloagentowość, automatyczne zatwierdzanie, integracja API
ze Stremio.

## Zasady produktu

-   Nie rekomenduj obejrzanych, obecnych na Plan to Watch ani niedawno
    odrzuconych tytułów.
-   Każda rekomendacja musi mieć identyfikatory źródłowe i krótkie
    uzasadnienie.
-   Ocena dopasowania jest heurystyką, nie prawdopodobieństwem.
-   Żadna operacja zapisu do Simkl bez jawnej decyzji użytkownika.
