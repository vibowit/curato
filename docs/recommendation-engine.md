# Recommendation Engine

## Cel

Wybierać tytuły pasujące do gustu użytkownika, a nie po prostu najwyżej
oceniane lub najpopularniejsze.

## Pipeline

1.  Użyj lokalnej kopii historii Simkl i Plan to Watch.
2.  Odczytaj aktywny profil gustu.
3.  Zbuduj pulę kandydatów z TMDB różnymi strategiami.
4.  Znormalizuj identyfikatory i metadane.
5.  Odrzuć obejrzane, obecne na Plan to Watch, wcześniej odrzucone i
    niedawno rekomendowane.
6.  Oblicz wstępny ranking.
7.  Poproś LLM o ocenę semantyczną wybranych kandydatów.
8.  Zastosuj dywersyfikację filmów/seriali i tematów.
9.  Zapisz wynik jako niezatwierdzony przebieg.

## Źródła kandydatów

Początkowa pula łączy 4 strategie odkrywania, z zachowaniem bezwzględnego parytetu mediów (`movie` vs `show`):
- **Podobne do ulubionych (Strategy A)**: pobiera niezależnie ulubione filmy oraz ulubione seriale użytkownika (osobne pule), aby zapobiec wypieraniu seriali przez filmy.
- **Preferencje gatunkowe (Strategy B)**: elastyczny resolver pojęć (`resolve_tmdb_genre_ids`) mapuje nazwy profilu (w tym złożone np. `Action/Thriller`, `History/War`) na właściwe identyfikatory TMDB osobno dla filmów i dla seriali.
- **Ulubieni twórcy (Strategy C)**: odpytuje TMDB zarówno o filmy, jak i o dorobek serialowy (`tv_credits`) reżyserów i showrunnerów.
- **Eksploracja (Strategy D)**: wysokiej jakości pozycje spoza dominujących gatunków dla obu typów mediów.

Udziały źródeł są parametrami konfiguracyjnymi, nie twardymi regułami.

## Ranking

Połącz: - dopasowanie do preferencji, - podobieństwo narracyjne i
tonalne, - jakość i kompletność metadanych, - ryzyka niedopasowania, -
różnorodność względem pozostałych propozycji.

LLM zwraca ustrukturyzowany JSON: identyfikator, score, confidence,
pozytywne czynniki, ryzyka i krótkie uzasadnienie. Waliduj odpowiedź
schematem; błędne wyniki ponów lub odrzuć.

`match_score` jest względną oceną modelu, nie prawdopodobieństwem
polubienia. `confidence` opisuje pewność wynikającą z jakości dostępnych
danych.

## Profil gustu

-   Preferencje długoterminowe i chwilowe zainteresowania przechowuj
    osobno.
-   W profilu zapisuj wagę i confidence każdej cechy.
-   Oceny obejrzanych pozycji są silniejszym sygnałem niż samo dodanie
    do To Watch.
-   Odrzucenie rekomendacji jest sygnałem, ale nie zawsze oznacza
    niechęć do całego gatunku.
-   Aktualizuj profil okresowo; zachowuj historię wersji i uzasadnienie
    zmian.
-   Pozwól użytkownikowi ręcznie skorygować profil.

## Dywersyfikacja i limity

Domyślnie: 10 filmów i 5 seriali na tydzień. Unikaj wielu niemal
identycznych propozycji. Nie filtruj według dostępności streamingowej.

## Zasady bezpieczeństwa

-   Nigdy nie dodawaj pozycji do Simkl podczas generowania.
-   Zapis następuje dopiero po jawnej akceptacji użytkownika.
-   Nie wymyślaj tytułów, dat ani faktów; rekomendacja musi mieć
    potwierdzone metadane i identyfikator.
-   Jeśli danych jest za mało, obniż confidence lub pomiń tytuł.
