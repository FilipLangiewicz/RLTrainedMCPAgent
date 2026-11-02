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
| 1 | `jira_search` | `jql`*, `fields`, `limit` | `{"total", "start_at", "max_results", "issues": [issue, ...]}` |
| 2 | `jira_get_issue` | `issue_key`*, `fields`, `comment_limit` | One issue (see "Issue"), with its comments |
| 3 | `jira_search_assignable_users` | `query`*, `project_key` | `{"success": true, "count", "users": [user, ...]}` |
| 4 | `jira_get_agile_boards` | `project_key` | `[{"id", "name", "type"}, ...]` |
| 5 | `jira_get_sprints_from_board` | `board_id`*, `state` | `[{"id", "name", "state", "start_date", "end_date", "goal"}, ...]` |
| 6 | `jira_get_transitions` | `issue_key`* | `[{"id", "name", "to_status"}, ...]` |
| 7 | `jira_get_worklog` | `issue_key`* | `{"worklogs": [{"id", "comment", "created", "updated", "started", "time_spent", "time_spent_seconds", "author"}, ...]}` |

### Write tools

| # | Tool | Used arguments | Result |
|---|---|---|---|
| 8 | `jira_create_issue` | `project_key`*, `summary`*, `issue_type`*, `assignee`, `description`, `additional_fields` | `{"message", "issue": issue}` |
| 9 | `jira_update_issue` | `issue_key`*, `fields`*, `return_fields` | `{"message": "Issue updated successfully", "issue": issue}` |
| 10 | `jira_transition_issue` | `issue_key`*, `transition_id`* | `{"message": "Issue <key> transitioned successfully", "issue": issue}` |
| 11 | `jira_add_comment` | `issue_key`*, `body`* | The new comment |
| 12 | `jira_add_worklog` | `issue_key`*, `time_spent`*, `comment` | `{"message": "Worklog added successfully", "worklog": {...}}` |
| 13 | `jira_add_issues_to_sprint` | `sprint_id`*, `issue_keys`* | `{"message": "Successfully added <n> issue(s) to sprint", ...}` |
| 14 | `jira_move_issues_to_backlog` | `issue_keys`* | `{"message": "Successfully moved <n> issue(s) to backlog", ...}` |

### Notes on the arguments

- `jql`: a JQL text, for example `project = WEB AND status = "In Progress" AND labels = frontend`.
- `fields` of `jira_update_issue`: a JSON text, not a JSON object. Example: `'{"assignee": "Anna Kowalczyk", "labels": ["frontend", "ui"]}'`.
- `assignee`: an e-mail, a display name or an account id. The server finds the account id. An unknown person gives an error.
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

The keys depend on the argument `fields`. Record real results on the Jira Cloud site before the implementation of the simulator (see `docs/JIRA_MCP.md`). Then the simulator can copy their format.

## Candidates for more tools

These tools are not in the selection. Each tool adds tokens to the prompt (the values are for Gemma 4).

| Tool | Tokens | Use |
|---|---|---|
| `jira_create_issue_link` and `jira_get_link_types` | 387 | Link two issues, for example "WEB-5 blokuje WEB-7". |
| `jira_link_to_epic` | 134 | Put an issue into an epic. The simulator must have epics. |
| `jira_delete_issue` | 85 | Delete an issue. A destructive operation. |
