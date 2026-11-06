# Report of baseline-gpt-oss-120b

Model: `gpt-oss-120b`. Time of the job: 357 s.

| Task type | Tasks | Score |
|---|---|---|
| All | 5 | 0.800 |
| `easy` | 3 | 1.000 |
| `multi_step` | 2 | 0.500 |

| Category | Tasks | Score |
|---|---|---|
| query | 5 | 0.800 |

Health: empty_answers 0, garbled_tasks 0, no_tool_call_tasks 0, invalid_call_tasks 0, max_steps_tasks 0, loop_same_tasks 0, loop_errors_tasks 0.

## What SFT and RL must teach

Write this section by hand: at most 6 short lines.

## Tasks

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Task | Category | Instruction | Calls | Answer of the model | Reason | Why | Points |
|---|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 1 | Obecnie zadanie WEB‑6 jest przypisane do **Ewy Mazur**. | the answer names Ewa Mazur |  | 1 |
| test-002 | query | Ile godzin poszło już na WEB-5? Pytam do raportu dla zarządu. Swoją drogą, ktoś znowu przestawił mi krzesło, wiem, że to nie przypadek. | 1 | Łącznie na zadaniu **WEB‑5** odnotowano **7,5 h** pracy. | expected 27000 s, found [27000] in the answer |  | 1 |
| test-003 | query | Jaki priorytet ma obecnie WEB-19? Proszę o krótką odpowiedź. | 1 | Priorytet WEB‑19 to **Highest**. | the answer contains 'Highest' |  | 1 |
| test-004 | query | Co z płatności jest jeszcze nieskończone w bieżącym sprincie? Wypisz mi to, bo na daily wszyscy patrzyli na mnie jak na kogoś, kto nie wie, a raczej nie chcę, żeby tak myśleli. | 1 | W bieżącym sprincie nadal otwarte są następujące zadania związane z płatnościami: - **WEB‑8** – „Nowe ikony metod płatności w checkout” – status **In review** - **WEB‑5** – „Integracja płatności BLIK” – status **In Progress** | missing keys: WEB-5, WEB-6 |  | 0 |
| test-005 | query | Ile bugów z priorytetem High lub Highest leży w backlogu bez sprintu? Potrzebuję samej liczby. | 5 | 3 bugi o priorytecie High lub Highest znajdują się w backlogu bez przypisanego sprintu. | the answer contains the number 3 |  | 1 |
