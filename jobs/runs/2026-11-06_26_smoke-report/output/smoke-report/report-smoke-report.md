# Report of smoke-report

Model: `gemma-4-e2b`. Time of the job: 35 s.

| Task type | Tasks | Score |
|---|---|---|
| All | 4 | 0.500 |
| `easy` | 1 | 0.000 |
| `multi_step` | 2 | 0.500 |
| `refusal` | 1 | 1.000 |

| Category | Tasks | Score |
|---|---|---|
| query | 1 | 0.000 |
| refusal | 1 | 1.000 |
| update | 1 | 0.000 |
| workflow | 1 | 1.000 |

Health: empty_answers 0, garbled_tasks 0, no_tool_call_tasks 0, invalid_call_tasks 0, max_steps_tasks 0, loop_same_tasks 0, loop_errors_tasks 0.

## What SFT and RL must teach

Write this section by hand: at most 6 short lines.

## Tasks

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Task | Category | Instruction | Calls | Answer of the model | Reason | Why | Points |
|---|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 1 | ODMOWA: Nie znalazłem żadnych zgłoszeń związanych z "WEB-6". Proszę podać dokładniejszy tytuł lub numer zgłoszenia, abym mógł sprawdzić, kto jest odpowiedzialny. | query task, but the answer is a refusal |  | 0 |
| test-010 | update | Klienci znowu skarżą się na wolne ładowanie listy zamówień w panelu. Niech zajmie się tym Ewa, i to z najwyższym priorytetem, bo mam dziś już trzy telefony w tej sprawie. | 1 | <\|"\|> | missing: {"field": "priority", "issue": "WEB-7", "value": "Highest"}, {"field": "assignee", "issue": "WEB-7", "value": "Ewa Mazur"} |  | 0 |
| test-039 | refusal | Czy możesz dać WEB-39 Ani? Ona chyba zna się na zdjęciach. | 1 | ODMOWA: Nie znalazłem użytkownika o imieniu Ani w systemie. | no change and the answer starts with ODMOWA: |  | 1 |
| test-112 | workflow | API-29 naprawione: zaloguj 2h, przestaw na In review i dodaj komentarz: Żądania HEAD nie liczą się już do limitu. | 4 | Issue API-29 został naprawiony, zalogowano 2h, przeniesiono do statusu "In review" i dodano komentarz: "Żądania HEAD nie liczą się już do limitu." | all 3 expected changes |  | 1 |
