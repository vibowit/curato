# Frontend UI/UX Guidelines (Curato)

## Estetyka i System Projektowy
- **Motyw**: Obsidian & Electric Indigo (`#090d16`, `#111827`, akcent `#6366f1`, szmaragd `#10b981` dla dopasowania/akceptacji, koral `#f43f5e` dla odrzucenia).
- **Ikonografia**: Używaj wyłącznie lekkich, monochromatycznych ikon **SVG (inline)**. Nie dodawaj kolorowych emoji systemowych do przycisków, nagłówków, badge'y ani toastów.
- **Zero zależności zewnętrznych**: Czysty HTML/CSS/Vanilla JS (bez bundlerów ani paczek npm).

## Układ i Ergonomia
- **Górny pasek (`header`)**: Zachowaj stałą, kompaktową wysokość (64px desktop, 56px mobile z rozwijanym menu hamburgerowym). Główne CTA (`+ Nowa Edycja`) zakotwiczone skrajnie po prawej.
- **Karty rekomendacji**:
  - Przycisk zwiastuna (`Play`) umieszczony jest na plakacie, aby nie zaśmiecać paska metryk.
  - Badge statusu decyzji na plakacie wyświetla się wyłącznie dla pozycji po decyzji (`status !== "pending"`).
  - Przycisk `Później` (`btn-later`) nie może mieć domyślnie klasy `.active` dla statusu `pending`.
- **Niezawodność**: Każde żądanie `fetch` w `app.js` musi korzystać z `AbortController` (limit czasu).
