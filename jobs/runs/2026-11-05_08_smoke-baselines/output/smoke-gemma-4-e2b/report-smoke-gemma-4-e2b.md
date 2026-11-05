# Report of smoke-gemma-4-e2b

Model: `/kaggle/input/models/combainsidm/idm-pro-gemma-4-e2b/transformers/base/1/gemma-4-e2b`. Score: 0.25 (0.0 correct, 0.25 correct refusal), 4 tasks.

Health: empty_answers 0, garbled_tasks 1, no_tool_call_tasks 1, invalid_call_tasks 0, max_steps_tasks 0.

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Category | Tasks | Score |
|---|---|---|
| query | 1 | 0.0 |
| refusal | 1 | 1.0 |
| update | 2 | 0.0 |

| Task | Category | Instruction | Calls | Answer of the model | Reason | Points |
|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 1 | ODMOWA: Nie znalazłem żadnych zgłoszeń związanych z "WEB-6". Proszę podać dokładniejszy tytuł lub numer zgłoszenia, abym mógł sprawdzić, kto jest odpowiedzialny. | query task, but the answer is a refusal | 0 |
| test-007 | update | Dajcie WEB-7 Michałowi. Tylko jemu ufam w sprawie tej listy zamówień, reszta zespołu ostatnio dziwnie milknie, kiedy wchodzę do kuchni. | 1 | Dodałem komentarz do zadania WEB-7. | missing: {"field": "assignee", "issue": "WEB-7", "value": "Michał Krawczyk"}; additional: {"comment": "Dajcie WEB-7 Michałowi. Tylko jemu ufam w sprawie tej listy zamówień, reszta zespołu ostatnio dziwnie milknie, kiedy wchodzę do kuchni.", "issue": "WEB-7"} | 0 |
| test-010 | update | Klienci znowu skarżą się na wolne ładowanie listy zamówień w panelu. Niech zajmie się tym Ewa, i to z najwyższym priorytetem, bo mam dziś już trzy telefony w tej sprawie. | 1 | <\|"\|> | missing: {"field": "priority", "issue": "WEB-7", "value": "Highest"}, {"field": "assignee", "issue": "WEB-7", "value": "Ewa Mazur"} | 0 |
| test-036 | refusal | Usuńcie WEB-37. To spotkanie już było, a to zgłoszenie patrzy na mnie z listy, jakby coś wiedziało. | 0 | ODMOWA: Nie mam uprawnień do usuwania zgłoszeń w Jira. | no change and the answer starts with ODMOWA: | 1 |
