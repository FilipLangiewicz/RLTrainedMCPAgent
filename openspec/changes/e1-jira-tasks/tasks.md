# Tasks

## 1. Environment

- [ ] 1.1 Write the Pydantic models of the board file in `src/environment.py` (project, board, person, sprint, issue, comment, worklog, `now`) and a load function. Verify: a test loads the 5 files `data/environments/test-{web,app,api,data,ops}.json` without an error, and a save and a load give an equal board.
- [ ] 1.2 Add the fixed values of D3 (statuses, categories, colors, transitions, types, priorities) and the checks of the allowed values. Verify: tests for a translated type (`Zadanie`), an unknown priority and a closed sprint give the errors of the spec.
- [ ] 1.3 Add the operations: create, change of fields, transition, comment, worklog (with the parse of the time and the 60 seconds case), sprint, backlog, all with the fixed clock. Verify: tests for the new key `WEB-41`, `Backlog` and `Medium` of a new issue, the transition `51`, a worklog of `1h 30m` = 5400 s, and two runs of the same calls give equal boards.
- [ ] 1.4 Add the person rules of D7: the match of a full name or an e-mail without regard to case and Polish letters, the word prefix search, no inactive persons. Verify: tests with "lukasz ostrowski", "Ewa" (error), "Ann" (two persons on `test-web`) and the inactive person Paweł Jasiński.
- [ ] 1.5 Add `diff(initial, final)` in the format of `expected.json` (D9). Verify: tests for no change, a changed assignee, a new comment, a new worklog and a new issue with a comment.

## 2. JQL subset

- [ ] 2.1 Create `src/jql.py` with the tokenizer, the parser and the evaluation of the subset of D8. Verify: unit tests for each field, each operator, `AND`/`OR`/`NOT`, parentheses and `ORDER BY`.
- [ ] 2.2 Add the semantics of the Jira Cloud site: `openSprints()` = active only, `~` = whole words, no `ORDER BY` = highest key first, `Cancelled` in the category `In Progress`, the error for a query without a condition, an empty result for a name that does not exist. Verify: one test for each rule of the spec "Search of issues" and "Status transitions".
- [ ] 2.3 Connect the JQL search to the environment. Verify: each JQL query of `data/tasks/test/solutions.json` runs on its board without an error.

## 3. MCP server and tools

- [ ] 3.1 Rewrite `src/tools.py` with the low-level server of D4: the 14 tools of `data/mcp_atlassian_tools.json`, `build_server(board)`, `apply_calls(board, calls)` and the stand-alone stdio mode. Verify: a test lists the tools with `mcp.Client` and compares the names, descriptions and schemas with the file.
- [ ] 3.2 Implement the 7 read tools with the result formats of D5. Verify: tests for the search result keys and `total: -1`, an issue with `Unassigned`, the comments of `jira_get_issue`, the assignable persons, the boards, the sprints, the transitions and the worklogs.
- [ ] 3.3 Implement the 7 write tools with the formats of D5 and the errors of D6, including the hidden errors. Verify: tests for each scenario of the spec `environment-tools`, and the board does not change after a failed call.
- [ ] 3.4 Add the contract test of D11 with `data/jira_recorded_results.json`. Verify: the test passes; each exception in the test has a reason.

## 4. Verifier

- [ ] 4.1 Rewrite `src/verifier.py`: the grades of normal tasks with the normalized multisets of D9, the grade of refusal tasks, the reason texts. Verify: tests for all scenarios of the spec `task-verifier` about changes and refusals.
- [ ] 4.2 Add the grade of `query` tasks and the answer checks for `keys`, `number`, `person`, `time` and `value`. Verify: tests for the scenarios of "Comparison of answers", and a test that each reference answer of the 30 test `query` tasks gives `correct`.

## 5. Task loader and checks

- [ ] 5.1 Rewrite `src/tasks.py`: the `Task` model, `load_tasks(split)` and the checks of the spec "Agreement of the task files". Remove the old generator. Verify: a test loads 200 test tasks; a missing train split gives an empty list; a test with a broken copy of the files gives an error with the task id.
- [ ] 5.2 Add the tests of the task set: counts and shares of difficulties, categories and difficulties, refusal kinds, the keys of `easy` tasks, different instruction texts, separate splits. Verify: the tests pass on the test set.
- [ ] 5.3 Add the test of the reference solutions (D10). Verify: all 200 tasks give `correct` or `correct_refusal`, and no reference call gives an error. If a task fails because of the data, correct the data file and write the correction into `docs/WORKLOG.md`.
- [ ] 5.4 Add the checksum test of the frozen test set for the three task files and the 5 boards. Skip it with the reason "test set not frozen yet" until the freeze. Verify: the test is skipped now, and a test with a changed copy shows that the comparison fails.

## 6. Model layer and prompts

- [ ] 6.1 Create `src/models.py` with the `Model` interface, `ModelOutput`, `make_model(config)` and the `ScriptedModel`. Move the backends out of `src/agent.py`. Verify: tests for `make_model` with each backend name, and errors for an unknown family and an unknown backend.
- [ ] 6.2 Add the families `qwen3.5`, `gemma4` and `bielik` (render and parse, D14). Read the chat templates of the models for the exact tool-call formats. Verify: parser tests with example outputs of each family (one call, two calls, broken arguments, text without a call, thinking text); render tests run only when the tokenizer files exist.
- [ ] 6.3 Add the `transformers` backend (local folder with `local_files_only=True`, or a Hugging Face id with a revision) and the `openai` backend. Verify: a test with a fake folder path checks the arguments of the load without a download; a test of the `openai` backend uses a fake client.
- [ ] 6.4 Add the thinking switch of D15. Verify: tests for the default `false`, `true` for `qwen3.5`, and the error for `bielik` with `true`.
- [ ] 6.5 Create `prompts/system-v2.md` (D12) and `prompts/tools-bielik-v1.md` (D14), and the load of a prompt by its version. Verify: tests for the default `v2`, the error for an unknown version, and the 14 tool names in the Bielik system prompt.

## 7. Agent and evaluation

- [ ] 7.1 Change `src/agent.py`: only the loop and the trajectory, the model through the interface of `src/models.py`, the prompt from a file, the default step limit 25. Verify: the agent tests pass with the `scripted` model, and a run records the prompt version and its SHA-256.
- [ ] 7.2 Change `src/evaluate.py` to the new loader, verifier and model layer. Record the family, the backend, the path, the revision and the thinking mode in `metrics.json`. Add the author to each line of `results.jsonl`. Verify: a new `tests/test_evaluate.py` runs the `scripted` model with the reference calls of 10 test tasks, gets the grade of the reference for each task, and checks the shards and the merge.

## 8. Removal and documentation

- [ ] 8.1 Remove the code of the old simulator and the old generator, and their tests. The old data is already removed. Verify: no test or module imports the old names (`list_users`, `generate_board`, `TEMPLATES`); all tests pass.
- [ ] 8.2 Correct `docs/TASKS.md` and `docs/JIRA_TOOLS.md` where the implementation found a difference. Add the config keys of a run (D14) to `docs/MODELS.md`. Add an entry to `docs/WORKLOG.md` with the changes and the number of tests. Verify: the documents agree with the code (formats, errors, answer types, config keys).

## 9. Integration

- [ ] 9.1 Run all tests with `uv run --no-project python -m pytest` and `openspec validate e1-jira-tasks --strict`. Verify: all tests pass (the checksum test is skipped) and the change is valid.
