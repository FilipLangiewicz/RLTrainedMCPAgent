# Tasks

## 1. Environment

- [x] 1.1 In `src/environment.py`, add the Pydantic models of a board (project key, persons, sprints, issues, comments), the allowed values, and save and load of JSON. Remove `src/.gitkeep` and `tests/.gitkeep`. Verify: a round-trip test in `tests/test_environment.py` passes.
- [x] 1.2 Add the board generator: the fixed lists of project keys, invented names with their Polish case forms, labels and title templates; 6 persons, 4 sprints, 30 to 40 issues. Verify: tests show that the same seed gives the same board and that the first names on a board are unique.
- [x] 1.3 Add the operations (create, update, labels, comment), the validation of values with clear error messages, the search with all filters, and `diff(before, after)` in the format of `design.md`. Verify: tests cover each scenario of `specs/environment/spec.md`.

## 2. Environment tools

- [x] 2.1 In `src/tools.py`, add `build_server(board)` with the seven tools of `specs/environment-tools/spec.md`. Raise `ToolError` for each expected error. Verify: tests in `tests/test_tools.py` connect with `mcp.Client(server)`, list the seven tools and call each tool.
- [x] 2.2 Add tests for tool errors and for two server instances with separate boards. Add the stdio start `python -m src.tools <board.json>`. Verify: the tests pass, and the command starts the server without an error.

## 3. Verifier

- [x] 3.1 In `src/verifier.py`, add `grade(task, initial_board, final_board, final_answer)` with the three grades, the reasons, the normalization of text, the label sets and the match of new issues by fields. Verify: tests in `tests/test_verifier.py` cover each scenario of `specs/task-verifier/spec.md`.

## 4. Task set

- [x] 4.1 In `src/tasks.py`, add the task model, load and save of JSONL, and the templates of the `easy` categories with more than one Polish text for each category. Verify: a test applies the reference solution of each `easy` template on a generated board and gets the grade `correct`.
- [x] 4.2 Add the templates of the `multi_step` categories. Verify: the same test passes for each `multi_step` template.
- [x] 4.3 Add the templates of the `refusal` categories with separate text lists for the test split and the train split. Verify: a test checks that each refusal task has no reference solution and no expected changes.
- [x] 4.4 Add the generator and its command `python -m src.tasks --seed 2026`. It writes the 25 boards and both task files, removes duplicates and tasks with an empty difference, and gives the sizes of `design.md`. Run it and commit the files in `data/`. Verify: tests check the counts by difficulty, the separate splits, the same output from two runs, and that the reference solution of each test task gets `correct`.
- [x] 4.5 Add the checksum test of the frozen test set in `tests/test_tasks.py`. Verify: the test passes, and it fails after a manual change of one line of a copy of the test file.

## 5. Agent loop

- [x] 5.1 In `src/agent.py`, add the system prompt with `PROMPT_VERSION = "v1"`, the trajectory model, the loop `run_task(...)` with the step limit, and the `scripted` backend for tests. Verify: tests in `tests/test_agent.py` with the `scripted` backend cover the final answer, the step limit and the trajectory record.
- [x] 5.2 Add the parser of Qwen3 tool calls and the handling of invalid calls. Verify: tests cover a correct call, two calls in one output, broken JSON and an unknown tool.
- [x] 5.3 Add the `transformers` backend: chat template with tools, `enable_thinking` from the config, greedy decoding, token counts. Verify: a test with the tokenizer of `Qwen/Qwen3-0.6B` checks that the chat template contains the tool schemas. Mark this test so that it skips when the Hub is not available.
- [x] 5.4 Add the `openai` backend with `base_url`, `model` and the API key from the environment variables or `.env`. Verify: a test with a fake client checks the conversion of tool calls and tool results.

## 6. Evaluation

- [x] 6.1 In `src/evaluate.py`, add `load_config(codename)` and `run_evaluation(cfg, output_dir, shard)`. It uses a fresh board for each task, grades each task, catches an exception in one task, and writes `results.jsonl` and `trajectories.jsonl`. Verify: tests in `tests/test_evaluate.py` with the `scripted` backend on 3 tasks check the files and the error case.
- [x] 6.2 Add `metrics.json` with the metrics and the record of the run of `specs/evaluation/spec.md`, the shards and the merge command. Verify: a test runs two shards with the `scripted` backend, merges them, and checks that each task occurs exactly one time and that the metrics are correct.
- [x] 6.3 Add the command line `python -m src.evaluate`. Do a local smoke test with `Qwen/Qwen3-0.6B`, `float32`, `--limit 2` and a temporary config outside the repository. Verify: the command ends and writes the three files. Do not commit the output.

## 7. Integration and records

- [x] 7.1 Run all tests with `uv run --no-project python -m pytest` and `ruff check src tests`. Verify: all tests pass and ruff reports no errors.
- [x] 7.2 Add an entry to `docs/WORKLOG.md` with the date and the changes: the six modules, the data files, the sizes of the task sets and the result of the smoke test. Verify: the entry exists and obeys the rules of Simplified Technical English.
