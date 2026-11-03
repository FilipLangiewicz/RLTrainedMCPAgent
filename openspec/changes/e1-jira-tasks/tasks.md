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

## 6. Agent and evaluation

- [ ] 6.1 Change `src/agent.py`: the prompt `v2` of D12 and the default step limit 25. Verify: the agent tests pass, and a run records the version `v2`.
- [ ] 6.2 Change `src/evaluate.py` to the new loader and verifier. Add the author to each line of `results.jsonl`. Verify: a test runs the `scripted` backend with the reference calls of 10 test tasks and gets the grade of the reference for each task.
- [ ] 6.3 Run a smoke test with `Qwen/Qwen3-0.6B` on the CPU for 2 test tasks. Verify: the run ends and writes the three result files. Record the time in `docs/WORKLOG.md`.

## 7. Removal and documentation

- [ ] 7.1 Remove the old boards (`data/environments/test-0*.json`, `train-*.json`), the old task files (`data/tasks/*/tasks.jsonl`) and the tests of the old simulator. Verify: `git ls-files data` shows only the new files and the two Jira files; all tests pass.
- [ ] 7.2 Correct `docs/TASKS.md` and `docs/JIRA_TOOLS.md` where the implementation found a difference. Add an entry to `docs/WORKLOG.md` with the changes and the number of tests. Verify: the documents agree with the code (formats, errors, answer types).

## 8. Integration

- [ ] 8.1 Run all tests with `uv run --no-project python -m pytest` and `openspec validate e1-jira-tasks --strict`. Verify: all tests pass (the checksum test is skipped) and the change is valid.
