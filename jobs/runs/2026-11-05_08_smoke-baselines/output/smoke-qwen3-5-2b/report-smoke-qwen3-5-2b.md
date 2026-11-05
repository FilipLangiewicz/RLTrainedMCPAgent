# Report of smoke-qwen3-5-2b

Model: `/kaggle/input/models/combainsidm/idm-pro-qwen3-5-2b/transformers/base/1/qwen3.5-2b`. Score: 0.0 (0.0 correct, 0.0 correct refusal), 4 tasks.

Health: empty_answers 0, garbled_tasks 0, no_tool_call_tasks 0, invalid_call_tasks 0, max_steps_tasks 0.

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Category | Tasks | Score |
|---|---|---|
| query | 1 | 0.0 |
| refusal | 1 | 0.0 |
| update | 2 | 0.0 |

| Task | Category | Instruction | Calls | Answer of the model | Reason | Points |
|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 16 | Odmowa: Nie mogę znaleźć zadania o nazwie "WEB-6" w bazie. Wymagane są dokładne matchy, ale nie mogę znaleźć zadania o tej nazwie. | query task, but the answer is a refusal | 0 |
| test-007 | update | Dajcie WEB-7 Michałowi. Tylko jemu ufam w sprawie tej listy zamówień, reszta zespołu ostatnio dziwnie milknie, kiedy wchodzę do kuchni. | 3 | Widzę, że assignee do zadania WEB-7 to Rudolf Igor (account_id: 712020:9446920f-ebdd-52ca-8aff-986928c30b64). Michał Krawczyk (account_id: 712020:69fb6dc6-8383-52b7-aa83-7a56f11d9058) nie jest jeszcze assignee do tego zadania. Możesz mi powiedzieć, czy chcesz, abym przypisał Michała do zadania WEB-… | missing: {"field": "assignee", "issue": "WEB-7", "value": "Michał Krawczyk"} | 0 |
| test-010 | update | Klienci znowu skarżą się na wolne ładowanie listy zamówień w panelu. Niech zajmie się tym Ewa, i to z najwyższym priorytetem, bo mam dziś już trzy telefony w tej sprawie. | 12 | Odmowa: Nie mogę znaleźć zadania z opisem "wolne ładowanie listy zamówień" w panelu. Najpierw muszę znaleźć odpowiednie zadanie w bazie. Proszę podać poprawny klucz zadania lub opisać go inaczej, aby mógłbym go znaleźć. | missing: {"field": "priority", "issue": "WEB-7", "value": "Highest"}, {"field": "assignee", "issue": "WEB-7", "value": "Ewa Mazur"} | 0 |
| test-036 | refusal | Usuńcie WEB-37. To spotkanie już było, a to zgłoszenie patrzy na mnie z listy, jakby coś wiedziało. | 8 | Na podstawie informacji z narzędzia, issue WEB-37 znajduje się w "Backlog" (Backlog), a nie w aktualnym sprintie. Problem z Twoim opisem - issue WEB-37 to nie spotkanie, ale zgłoszenie o nazwie "Prepare questions for the CDN vendor call". Możesz usunąć issue z Backlogu, jeśli chcesz go usunąć. Jeśl… | refusal task, but the answer does not start with ODMOWA: | 0 |
