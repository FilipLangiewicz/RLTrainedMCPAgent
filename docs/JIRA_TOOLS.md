# Contracts of the selected Jira tools

This file describes the tools of `mcp-atlassian` 0.23.1 that the project uses. The simulator must give these tools with the same names, arguments and result formats. See `docs/JIRA_MCP.md` for the server, the version and the full list of tools.

The exact JSON schemas are in `data/mcp_atlassian_tools.json`. The file is a copy of the `tools/list` result of the real server. If this file and the JSON file do not agree, the JSON file is correct.

This file is a proposal. The team must agree on the final list.

## Rules

1. The simulator uses the names, the descriptions and the argument schemas from `data/mcp_atlassian_tools.json` without a change. Thus the model sees the same tools on the simulator and on real Jira.
2. Each operation has one way. If the real server has two ways, the project uses only the way in the table "Operations".
3. Each tool also has arguments that the project does not use. The simulator accepts them in the schema, but the tasks and the reference solutions do not use them.
4. Each tool returns a JSON text. The simulator returns the same keys as the real server.

## Operations

| Operation | Tools | Other way that the project does not use |
|---|---|---|
| Find issues | `jira_search` | `jira_get_project_issues`, `jira_get_board_issues`, `jira_get_sprint_issues` |
| Read one issue | `jira_get_issue` | none |
| Create an issue | `jira_create_issue` | `jira_batch_create_issues` |
| Assign a person | `jira_search_assignable_users`, then `jira_update_issue` with `{"assignee": ...}` | `jira_assign_issue`; the `assignee` argument of `jira_create_issue` for a new issue is permitted |
| Change the status | `jira_get_transitions`, then `jira_transition_issue` | `jira_update_issue` with `{"status": ...}` |
| Add or remove a label | `jira_get_issue`, then `jira_update_issue` with the full list `{"labels": [...]}` | none |
| Change the priority, the summary or the description | `jira_update_issue` | none |
| Add a comment | `jira_add_comment` | the `comment` argument of `jira_transition_issue` |
| Log work time | `jira_add_worklog` | none |
| Read the logged time | `jira_get_worklog` | the argument `include=worklogs` of `jira_get_issue` |
| Move an issue to a sprint | `jira_get_agile_boards`, `jira_get_sprints_from_board`, then `jira_add_issues_to_sprint` | the sprint custom field in `additional_fields` of `jira_update_issue` |
| Move an issue to the backlog | `jira_move_issues_to_backlog` | none |

## Size

The size is the number of tokens that the tool schemas add to the prompt. The measurement uses the chat template of each model with all 14 tools.

| Model | 14 selected tools | All 63 Jira tools |
|---|---|---|
| `Qwen/Qwen3.5-2B` | 4806 | 15708 |
| `google/gemma-4-E2B-it` | 3904 | 12979 |

The Bielik tokenizer is in a gated repository on Hugging Face. The measurement for Bielik needs an account that accepted the license.

## Tools (14)

The column "Used arguments" gives the arguments that the tasks use. A star (*) marks a required argument.

### Read tools

| # | Tool | Used arguments | Result |
|---|---|---|---|
| 1 | `jira_search` | `jql`*, `fields`, `limit` | `{"total": -1, "start_at", "max_results", "issues": [issue, ...]}` |
| 2 | `jira_get_issue` | `issue_key`*, `fields`, `comment_limit` | One issue (see "Issue"), with its comments |
| 3 | `jira_search_assignable_users` | `query`*, `project_key` | `{"success": true, "count", "users": [user, ...]}` |
| 4 | `jira_get_agile_boards` | `project_key` | `[{"id", "name", "type"}, ...]` |
| 5 | `jira_get_sprints_from_board` | `board_id`*, `state` | `[{"id", "name", "state", "start_date", "end_date", "goal"}, ...]` |
| 6 | `jira_get_transitions` | `issue_key`* | `[{"id": <number>, "name"}, ...]` |
| 7 | `jira_get_worklog` | `issue_key`* | `{"worklogs": [{"id", "comment", "created", "updated", "started", "time_spent", "time_spent_seconds", "author"}, ...]}` |

### Write tools

| # | Tool | Used arguments | Result |
|---|---|---|---|
| 8 | `jira_create_issue` | `project_key`*, `summary`*, `issue_type`*, `assignee`, `description`, `additional_fields` | `{"message", "issue": issue}` |
| 9 | `jira_update_issue` | `issue_key`*, `fields`*, `return_fields` | `{"message": "Issue updated successfully", "issue": issue}` |
| 10 | `jira_transition_issue` | `issue_key`*, `transition_id`* | `{"message": "Issue <key> transitioned successfully", "issue": issue}` |
| 11 | `jira_add_comment` | `issue_key`*, `body`* | `{"id", "body", "created", "author"}` |
| 12 | `jira_add_worklog` | `issue_key`*, `time_spent`*, `comment` | `{"message": "Worklog added successfully", "worklog": {...}}` |
| 13 | `jira_add_issues_to_sprint` | `sprint_id`*, `issue_keys`* | `{"message": "Successfully added <n> issue(s) to sprint", ...}` |
| 14 | `jira_move_issues_to_backlog` | `issue_keys`* | `{"message": "Successfully moved <n> issue(s) to backlog", ...}` |

### Notes on the arguments

- `jql`: a JQL text, for example `project = WEB AND status = "In Progress" AND labels = frontend`.
- `fields` of `jira_update_issue`: a JSON text, not a JSON object. Example: `'{"assignee": "Anna Kowalczyk", "labels": ["frontend", "ui"]}'`.
- `assignee`: an e-mail, a display name or an account id. The server finds the account id. An unknown person gives an error in `jira_update_issue`. In `jira_create_issue`, an unknown person gives no error (see "Behavior of real Jira").
- `labels`: the full list. The new list replaces the old list. To add one label, the model reads the old list first.
- `priority` in `fields` or `additional_fields`: `{"priority": {"name": "High"}}`.
- `return_fields`: the default is `*all`, and the result can be large. The value `key,status` makes a short result.
- `transition_id`: the id from `jira_get_transitions`, for example `"21"`. The ids depend on the workflow of the project.
- `issue_keys`: one text with keys and commas, for example `"WEB-1,WEB-2"`.
- `time_spent`: the Jira format, for example `"1h 30m"`, `"2h"`, `"1d"`.
- `body` and `description`: Markdown text.

### Issue

`issue` is the result of `JiraIssue.to_simplified_dict()` (`src/mcp_atlassian/models/jira/issue.py`). The main keys:

- `id`, `key`, `summary`, `description`
- `status`, `issue_type`, `priority`
- `assignee`, `reporter`, `labels`
- `created`, `updated`
- `comments` (only in `jira_get_issue`)

The keys depend on the argument `fields`. If an issue has no assignee, the result has `"assignee": {"display_name": "Unassigned"}`, not `null`.

## Behavior of real Jira

On 2026-11-03 we ran all 14 tools on the Jira Cloud site. `data/jira_recorded_results.json` has 43 calls with their real results and errors. The simulator must copy this behavior.

### Language of Jira

The team decision: the Jira language of the API account is English (`en_US`). The issues, the comments and the tasks can be in Polish or in English.

Jira translates the system names into the Jira language of the account. With the language `pl_PL`, the results showed `W toku` and `Zadanie`, but JQL accepted only `In Progress` and `Task`. A JQL with a translated name gave no error and returned no issues. With English, the results and JQL use the same names:

| Thing | Names |
|---|---|
| Status | `Backlog`, `In Progress`, `In review`, `Cancelled`, `Done` |
| Transition | `Backlog` (11), `In Progress` (21), `In review` (31), `Cancelled` (41), `Done` (51) |
| Status category | `To Do`, `In Progress`, `Done` |
| Issue type | `Task`, `Epic`, `Subtask` |
| Priority | `Highest`, `High`, `Medium`, `Low`, `Lowest` |

To set the Jira language of the account, send `PUT /rest/api/3/mypreferences/locale` with `{"locale": "en_US"}`. The profile of the Atlassian account can keep a different language.

The text of the users does not change. Thus a Polish summary stays Polish.

A translated name is now an error of the model. `status = "W toku"` returns an empty list without an error. `jira_create_issue` with `issue_type` `Zadanie` gives the error "Specify a valid issue type".

### Other facts

- `jira_search` always returns `"total": -1`. The search API of Jira Cloud does not give the number of results.
- `sprint in openSprints()` finds only issues in the active sprint. `sprint in futureSprints()` finds the issues in future sprints.
- `summary ~` and `text ~` find whole words. Polish forms do not match: `summary ~ "zadania"` does not find "Zadanie 1".
- Without `ORDER BY`, the search result starts with the highest key.
- The status category of `Cancelled` on this site is `In Progress`. Thus `statusCategory != Done` also finds the `Cancelled` issues.
- A JQL without a condition (for example `ORDER BY created DESC`) gives the error "Unbounded JQL queries are not allowed here. Please add a search restriction to your query.".
- `jira_create_issue` with an unknown `assignee` creates the issue without an assignee. The result shows no error.
- `jira_add_worklog` with an incorrect `time_spent` (for example "półtorej godziny") logs `1m`. The result shows no error.
- A new issue without a priority gets `Medium`.
- A person without access to Jira is not in the results of `jira_search_assignable_users`.
- The server changes Markdown to the Jira format and back. The result of `jira_create_issue` and `jira_update_issue` shows the Jira wiki format (`*bold*`). `jira_get_issue` shows Markdown (`**bold**`). `jira_search` and `jira_add_comment` lose the format (bold text goes onto a separate line).
- The dates in the results use the time zone of the computer that runs the server. On Windows with the Polish language, a date is `2026-11-02 23:55:34 Środkowoeuropejski czas stand.`. The dates of comments and worklogs have the ISO format (`2026-11-03 21:01:02.367000+01:00`).
- The default value of `fields` in the schemas of `jira_search` and `jira_get_issue` has a different order of fields after each start of the server. The server makes it from a Python set.

## Candidates for more tools

These tools are not in the selection. Each tool adds tokens to the prompt (the values are for Gemma 4).

| Tool | Tokens | Use |
|---|---|---|
| `jira_create_issue_link` and `jira_get_link_types` | 387 | Link two issues, for example "WEB-5 blokuje WEB-7". |
| `jira_link_to_epic` | 134 | Put an issue into an epic. The simulator must have epics. |
| `jira_delete_issue` | 85 | Delete an issue. A destructive operation. |
