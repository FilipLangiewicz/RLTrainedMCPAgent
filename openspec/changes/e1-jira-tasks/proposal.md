# Proposal

## Why

The team selected `mcp-atlassian` 0.23.1 as the contract for real Jira, but the simulator still gives 7 tools of our own design. Thus a model that learns on the simulator cannot use real Jira without a change. The old task set is also weak: it uses few templates, it gives the issue key in almost each instruction, it has no questions about data, and its refusals are easy. E1 (2026-11-16) needs a frozen test set and a baseline, so the new simulator and the new task set must come now.

## What Changes

- **BREAKING** The environment gets the data model of real Jira: issues with Jira fields, worklogs, persons with account ids, one agile board, sprints with dates, the statuses and transitions of the Jira Cloud site. The old field values (`to_do`, `critical` and others) go away.
- **BREAKING** The MCP server gives the 14 tools of `data/mcp_atlassian_tools.json` with the same names, descriptions and argument schemas. The old 7 tools go away.
- The tools return the same keys, formats and error messages as the real server (`data/jira_recorded_results.json`). The simulator also copies the errors that real Jira hides, for example an unknown assignee in the create tool.
- The search tool accepts a subset of JQL.
- A contract test runs the recorded calls on the simulator and compares the results with the recorded results.
- The board generator takes the texts of issues and comments from a content file. The texts are in Polish and in English.
- **BREAKING** The task set gets 8 categories: `query`, `update`, `log`, `create`, `sprint`, `bulk`, `workflow`, `refusal`. The difficulty (`easy`, `multi_step`, `refusal`) stays as a second axis.
- The generator makes task drafts without text. The instruction texts are written in a separate step into a text file. A check of the generator makes sure that each text names what the task needs. The team reviews all texts of both splits.
- **BREAKING** New boards, a new train set and a new test set replace the old data. The new test set is frozen with a new checksum.
- The verifier grades the tasks of the category `query`: it compares the final answer with the expected answer, and the board must not change.
- The system prompt gets the version `v2`. It tells the model that the names of statuses, issue types and priorities are in English.
- Add `docs/TASKS.md`: the description of the task set for the team, with diagrams and tables.

## Out of scope

- The adapter that runs the agent on the real Jira site, and the data for the test on real Jira (E3).
- The parsers of the tool calls for the new candidate models (Qwen3.5, Bielik, Gemma 4) and the new baseline. A separate change or job does this work.
- Tools that are not in `data/mcp_atlassian_tools.json`, and the arguments of the 14 tools that the tasks do not use. The simulator accepts these arguments, but it can ignore them.
- Full JQL. The simulator supports only the subset in the design.
- Training (SFT, RL).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environment`: the data model of real Jira, the content file, worklogs, the statuses and transitions, the board for the contract test.
- `environment-tools`: the 14 tools of the real server, the result formats, the errors, the subset of JQL, the contract test.
- `task-set`: the 8 categories, the drafts and the text file, the review, the new counts, the new rules for the words of a user.
- `task-verifier`: the grade of a `query` task, the comparison of worklogs and sprints, the refusal for an ambiguous person.
- `agent-loop`: the system prompt `v2`.

## Impact

- Code: `src/environment.py`, `src/tools.py`, `src/tasks.py` and `src/verifier.py` change almost fully. `src/agent.py` gets the new prompt. `src/evaluate.py` changes only a little.
- Tests: all test files change. A new contract test uses `data/jira_recorded_results.json`.
- Data: all files in `data/environments/` and `data/tasks/` are new. New files: the content file and the text files of the two splits (see the design).
- Docs: new `docs/TASKS.md`. `docs/WORKLOG.md` gets an entry.
- The results of `baseline-v1` do not apply to the new test set.
- Dependencies: no new package.
