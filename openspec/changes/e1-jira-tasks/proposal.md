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
- The system prompt gets the version `v2`. It tells the model that the names of statuses, issue types and priorities are in English.
- The evaluation uses the new loader. A missing train split is not an error.

## Out of scope

- The making of the task data. The test set exists already, and the train set comes later in the same format. This change does not generate tasks.
- The adapter that runs the agent on the real Jira site (E3).
- The parsers of the tool calls for the new candidate models (Qwen3.5, Bielik, Gemma 4) and the new baseline. A separate change or job does this work.
- Tools that are not in `data/mcp_atlassian_tools.json`, and the arguments that the tasks do not use. The simulator accepts these arguments, but it can ignore them.
- Full JQL. The simulator supports only the subset in the design.
- Training (SFT, RL).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environment`: the board files in the Jira format, the statuses and transitions, the subset of JQL, worklogs, the fixed clock, the difference of two states in the format of `expected.json`.
- `environment-tools`: the 14 tools of the real server, the result formats, the errors, the hidden errors, the contract test.
- `task-set`: the three task files, the categories, the refusal kinds, the authors, the checks of the loader, the test of the reference solutions. No generator.
- `task-verifier`: the comparison with `expected.json`, the grade of a `query` task, the answer types.
- `agent-loop`: the system prompt `v2`.

## Impact

- Code: `src/environment.py`, `src/tools.py`, `src/tasks.py` and `src/verifier.py` change almost fully. A new file `src/jql.py` has the parser of the JQL subset (see the design). `src/agent.py` gets the new prompt. `src/evaluate.py` changes a little.
- Tests: all test files change. The contract test uses `data/jira_recorded_results.json`.
- Data: the old boards (`data/environments/test-0*.json`, `train-*.json`) and the old task files (`data/tasks/*/tasks.jsonl`) are removed. The new test boards and task files stay without a change.
- Docs: `docs/TASKS.md` and `docs/JIRA_TOOLS.md` get small corrections if the implementation finds a difference. `docs/WORKLOG.md` gets an entry.
- The results of `baseline-v1` do not apply to the new test set.
- Dependencies: no new package.
