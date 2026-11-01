# Projekt semestralny: system oparty na LLM

Tekst ze slajdów prowadzącego (oryginał). Screeny slajdów: [slides/](slides/).

## Etapy

| Etap | Opis | Termin |
|---|---|---|
| E1 – System bazowy | Działa end-to-end na wybranym zakresie danych (przy fine-tuningu: model bazowy + prompt) + zestaw testowy (wejście → oczekiwany wynik) i wynik bazowy. | 16 XI 2026 |
| E2 | Np. zaawansowany RAG / fine-tuning – wynik przed/po na tym samym zestawie. | 7 XII 2026 |
| E3 | Np. model wybiera narzędzia; porównanie z E2 na tym samym zestawie. | 21 XII 2026 |
| ★ Demo Day + spotkanie oceniające z prowadzącym | Demo działającego systemu + spotkanie z prowadzącym (ustalane indywidualnie). | 11 I 2027 |

## Co budujemy?

- Dowolny system oparty na LLM: w szczególności oparty RAG, model poddany fine-tuning'owi.
- Grupa proponuje temat i zakres danych.
- Lokalnie (Ollama – inferencja) lub zdalnie (API / chmura).
- Przykład kierunku: starter RAG + demo „Regulamin studiów PW” – można z niego wystartować, nie trzeba.

## Zasady

- Zespół: 2 osoby (maks. 3).
- Dane: dowolny rozsądnie dopasowany do zadania zbiór; bez danych osobowych.
- Narzędzia: dowolne, w tym asystenci AI do kodowania (Claude Code, Codex, Cursor…). Zespół odpowiada za cały kod i potrafi go wyjaśnić.

## Ocena

- działający system
- pomiar przed/po na tym samym zestawie testowym (rozłącznym z danymi do fine-tuningu)
- analiza błędów
- prezentacja i rozmowa
- wystąpienie na Demo Day (każdy zespół 3 min. showcase + 3 min. pytania)

## Ewaluacja

**Zestaw testowy (golden set)** – wejście + oczekiwany wynik

- Przygotowany przed etapami ulepszania; porównania na tej samej wersji – po rozbudowie przeliczamy wszystkie warianty.
- Różne trudności: łatwe · kilka źródeł/kroków · spoza zakresu → odmowa.
- RAG: także źródła – miejsca w dokumentach, nie chunki.
- Fine-tuning: testowe rozłączne z treningowymi (odłożone przed treningiem).
- Minimum na start: ręczna ocena – poprawna / błędna / poprawna odmowa.

**Jak mierzymy**

- Jedna zmiana naraz – ten sam zestaw, reszta konfiguracji bez zmian.
- Powtarzalność: temperature = 0 (jeśli model/API pozwala, minimalizacja losowości); zapisuj konfigurację, wersję modelu i wyniki.
- Transparentnie: podobny budżet kontekstu, nie to samo k; czas i koszt obok jakości.
- Wielkość zbioru → małe różnice to często szum; sprawdź, które przykłady się zmieniły.
- W szczególności: wielkość modelu mierzona liczbą parametrów nie jest zmienną w ocenie projektu / testu / ewaluacji.

> Każda zmiana = pomiar przed/po na tym samym zestawie testowym – inaczej nie wiemy, czy pomogła.

## Starter RAG

[github.com/kzbikowski/idm-rag-starter](https://github.com/kzbikowski/idm-rag-starter) – starter = przykład, nie obowiązkowa baza.
