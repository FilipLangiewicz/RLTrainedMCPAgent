# Proposal

## Why

The team selected `mcp-atlassian` 0.23.1 as the contract for real Jira, but the simulator still gives 7 tools of our own design. Thus a model that learns on the simulator cannot use real Jira without a change. The new test set (`data/tasks/test/`, see `docs/TASKS.md`) already uses the 14 real tools, but no code can run it. E1 (2026-11-16) needs a baseline on this test set, so the simulator, the verifier and the loader of the task files must come now.

## What Changes

- **BREAKING** The environment uses the board files of `data/environments/` in the new format: the data model of a Jira Cloud project with persons, sprints, issues, comments and worklogs. The old board model and its values (`to_do`, `critical` and others) go away.
- **BREAKING** The MCP server gives the 14 tools of `data/mcp_atlassian_tools.json` with the same names, descriptions and argument schemas. The old 7 tools go away.
- The tools return the keys, the formats and the error messages of the real server (`data/jira_recorded_results.json`). They also copy the errors that real Jira hides, for example an unknown assignee in the create tool.
- The search tool accepts a subset of JQL with the semantics of the Jira Cloud site.
- A contract test runs the recorded calls on the simulator and compares the results with the recorded results.
- **BREAKING** The task loader reads the task files of a split: `queries.json`, `solutions.json` and `expected.json`. The old file `tasks.jsonl` and the old task generator go away.
- The loader checks the task files: the three files agree, the categories and the counts are correct, and the two splits are separate.
- A test applies each reference solution of the test set to its board with the simulator. The result must be equal to `expected.json`.
- The verifier compares the changes of the board with the changes in `expected.json`. It also grades the tasks of the category `query`: it compares the final answer with the expected answer.
- A model layer goes between the agent loop and the models. The agent loop knows only one interface. A model family gives the chat format, the parser of the tool calls and the thinking switch. A backend runs the model: `transformers`, an OpenAI-compatible API or a script for the tests. The families are `qwen3.5`, `gemma4` and `bielik`.
- The thinking mode comes from the config of a run (`model.thinking`), not from `.env`. Thus `metrics.json` records it.
- **BREAKING** The system prompts move out of `src/agent.py` into versioned files in `prompts/`. The config of a run gives the version. The new version is `v2`. It tells the model that the names of statuses, issue types and priorities are in English.
- The evaluation uses the new loader. A missing train split is not an error.

## Out of scope

- The making of the task data. The test set exists already, and the train set comes later in the same format. This change does not generate tasks.
- The adapter that runs the agent on the real Jira site (E3).
- The download of the model weights and their storage as Kaggle Models. Separate Kaggle jobs do this work, one job for each model.
- Runs of the real models: the smoke tests on a GPU and the new baseline. Kaggle jobs do this work after the change. The tests of this change use no model weights.
- Tools that are not in `data/mcp_atlassian_tools.json`, and the arguments that the tasks do not use. The simulator accepts these arguments, but it can ignore them.
- Full JQL. The simulator supports only the subset in the design.
- Training (SFT, RL).

## Capabilities

### New Capabilities

- `model-layer`: one interface for all models, the model families with their chat formats and tool-call parsers, the backends, the thinking switch from the config of a run.

### Modified Capabilities

- `environment`: the board files in the Jira format, the statuses and transitions, the subset of JQL, worklogs, the fixed clock, the difference of two states in the format of `expected.json`.
- `environment-tools`: the 14 tools of the real server, the result formats, the errors, the hidden errors, the contract test.
- `task-set`: the three task files, the categories, the refusal kinds, the authors, the checks of the loader, the test of the reference solutions. No generator.
- `task-verifier`: the comparison with `expected.json`, the grade of a `query` task, the answer types.
- `agent-loop`: the system prompt from a versioned file, the version `v2`. The backends and the generation settings move to `model-layer`.

## Impact

- Code: `src/environment.py`, `src/tools.py`, `src/tasks.py` and `src/verifier.py` change almost fully. New files: `src/jql.py` (the JQL subset) and `src/models.py` (the model layer). `src/agent.py` keeps only the loop and the trajectory. `src/evaluate.py` changes a little.
- Prompts: a new folder `prompts/` with `system-v2.md` and `tools-bielik-v1.md`.
- Tests: all test files change. The contract test uses `data/jira_recorded_results.json`.
- Data: the old boards, the old task files and their two test files were removed on 2026-11-05, before this change. The new test boards and task files stay without a change.
- Docs: `docs/TASKS.md` and `docs/JIRA_TOOLS.md` get small corrections if the implementation finds a difference. `docs/WORKLOG.md` gets an entry.
- The results of `baseline-v1` do not apply to the new test set.
- Dependencies: no new package.
