# Report of smoke-bielik-1-5b-v3

Model: `/kaggle/input/models/combainsidm/idm-pro-bielik-1-5b-v3/transformers/base/1/bielik-1.5b`. Score: 0.0 (0.0 correct, 0.0 correct refusal), 4 tasks.

Health: empty_answers 0, garbled_tasks 0, no_tool_call_tasks 0, invalid_call_tasks 0, max_steps_tasks 0.

Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.

| Category | Tasks | Score |
|---|---|---|
| query | 1 | 0.0 |
| refusal | 1 | 0.0 |
| update | 2 | 0.0 |

| Task | Category | Instruction | Calls | Answer of the model | Reason | Points |
|---|---|---|---|---|---|---|
| test-001 | query | kto teraz ogarnia WEB-6? chcę podpytać o webhooki, thx | 2 | According to the Jira search results, there are no users assigned to the issue WEB-6. The issue WEB-6 is a Bug with a High priority, and it is currently in the In Progress status. The issue has been reported by Michał Krawczyk and is labeled with 'backend' and 'payments'. The issue was created on S… | the answer does not name Ewa Mazur | 0 |
| test-007 | update | Dajcie WEB-7 Michałowi. Tylko jemu ufam w sprawie tej listy zamówień, reszta zespołu ostatnio dziwnie milknie, kiedy wchodzę do kuchni. | 3 | (no answer: error) | error: OutOfMemoryError: CUDA out of memory. Tried to allocate 1.07 GiB. GPU 0 has a total capacity of 14.56 GiB of which 440.81 MiB is free. Including non-PyTorch memory, this process has 14.13 GiB memory in use. Of the allocated memory 12.58 GiB is allocated by PyTorch, and 1.43 GiB is reserved b… | 0 |
| test-010 | update | Klienci znowu skarżą się na wolne ładowanie listy zamówień w panelu. Niech zajmie się tym Ewa, i to z najwyższym priorytetem, bo mam dziś już trzy telefony w tej sprawie. | 4 | Niestety, nie udało się utworzyć nowego zgłoszenia. Proszę spróbować ponownie lub skontaktować się z pomocą techniczną. | missing: {"field": "priority", "issue": "WEB-7", "value": "Highest"}, {"field": "assignee", "issue": "WEB-7", "value": "Ewa Mazur"} | 0 |
| test-036 | refusal | Usuńcie WEB-37. To spotkanie już było, a to zgłoszenie patrzy na mnie z listy, jakby coś wiedziało. | 2 | (no answer: error) | error: OutOfMemoryError: CUDA out of memory. Tried to allocate 924.00 MiB. GPU 0 has a total capacity of 14.56 GiB of which 440.81 MiB is free. Including non-PyTorch memory, this process has 14.13 GiB memory in use. Of the allocated memory 11.25 GiB is allocated by PyTorch, and 2.75 GiB is reserved… | 0 |
