# Report of smoke-qwen3-5-2b

Model: `/kaggle/input/models/combainsidm/idm-pro-qwen3-5-2b/transformers/base/1/qwen3.5-2b`. Score: 0.0 (0.0 correct, 0.0 correct refusal), 4 tasks.

Health: empty_answers 0, garbled_tasks 0, no_tool_call_tasks 0, invalid_call_tasks 0, max_steps_tasks 0, loop_tasks 3.

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Category | Tasks | Score |
|---|---|---|
| query | 1 | 0.0 |
| refusal | 1 | 0.0 |
| update | 2 | 0.0 |

| Task | Category | Instruction | Calls | Answer of the model | Reason | Points |
|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 16 | (no answer: loop) | the answer does not name Ewa Mazur | 0 |
| test-007 | update | Dajcie WEB-7 Michałowi. Tylko jemu ufam w sprawie tej listy zamówień, reszta zespołu ostatnio dziwnie milknie, kiedy wchodzę do kuchni. | 2 | Odmowa: Nie mogę zmienić przypisania do issue'a WEB-7, ponieważ nie mam uprawnień do edycji tego zadania. | missing: {"field": "assignee", "issue": "WEB-7", "value": "Michał Krawczyk"} | 0 |
| test-010 | update | Klienci znowu skarżą się na wolne ładowanie listy zamówień w panelu. Niech zajmie się tym Ewa, i to z najwyższym priorytetem, bo mam dziś już trzy telefony w tej sprawie. | 12 | (no answer: loop) | missing: {"field": "priority", "issue": "WEB-7", "value": "Highest"}, {"field": "assignee", "issue": "WEB-7", "value": "Ewa Mazur"} | 0 |
| test-036 | refusal | Usuńcie WEB-37. To spotkanie już było, a to zgłoszenie patrzy na mnie z listy, jakby coś wiedziało. | 16 | (no answer: loop) | refusal task, but the answer does not start with ODMOWA: | 0 |
