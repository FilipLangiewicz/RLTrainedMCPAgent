# Jira MCP server: mcp-atlassian

The project uses the MCP server `mcp-atlassian` as the reference for real Jira. The simulator must give the same tools as this server. Then the model can use the same tools on the simulator and on real Jira.

Date of the research: 2026-11-02.

## Pinned version

| Property | Value |
|---|---|
| Name | `mcp-atlassian` |
| Version | **0.23.1** |
| Release date | 2026-08-19 (upload to PyPI). This is the last version on PyPI on 2026-11-02. |
| Repository | https://github.com/sooperset/mcp-atlassian |
| Package | https://pypi.org/project/mcp-atlassian/0.23.1/ |
| Documentation | https://mcp-atlassian.soomiles.com/docs |
| Source file of the Jira tools | `src/mcp_atlassian/servers/jira.py` |
| sdist | `mcp_atlassian-0.23.1.tar.gz` |
| SHA-256 of the sdist | `6b57391928887f5334fe854073b09e3a49bb7dae0d55a1b1276f4d910607a0f1` |
| Owner | sooperset (Hyeonsoo Lee). This is a community project. Atlassian does not support it. |
| License | MIT |
| Language | Python 3.10 or newer. It uses `fastmcp` 3.x and `mcp` 1.x. |
| Start | `uvx mcp-atlassian==0.23.1` or Docker (`ghcr.io/sooperset/mcp-atlassian`) |
| Transports | stdio, SSE, streamable HTTP |
| Tools | 63 Jira tools in 16 toolsets, and 35 Confluence tools |

Use only this version. A new version can change the names, the arguments or the descriptions of the tools. To change the version, do the check in "How we checked the data" again.

## Supported Jira versions

| Jira | Authentication | Free option |
|---|---|---|
| Jira Cloud | `JIRA_URL`, `JIRA_USERNAME` (e-mail), `JIRA_API_TOKEN` | The Free plan: up to 10 users, 2 GB of storage. |
| Jira Server / Data Center | `JIRA_URL`, `JIRA_PERSONAL_TOKEN` | No. Atlassian stopped the sale of new Data Center licenses on 2026-03-30. Since that date, a user cannot make a trial license. |

Thus the test on real Jira uses Jira Cloud with the Free plan.

Sources:

- Jira prices: https://www.atlassian.com/en/software/jira/pricing
- Data Center trial license: https://confluence.atlassian.com/adminjiraserver101/get-a-jira-data-center-trial-license-1455428029.html

## How the tool list operates

- The server adds the prefix `jira_` to each Jira tool, for example `jira_get_issue`. The code does this with `main_mcp.mount(jira_mcp, namespace="jira")`.
- `ENABLED_TOOLS` gives a list of the permitted tool names, for example `ENABLED_TOOLS=jira_search,jira_get_issue`.
- `TOOLSETS` selects groups of tools. `TOOLSETS=default` gives 4 Jira toolsets: `jira_issues`, `jira_fields`, `jira_comments`, `jira_transitions`.
- When `TOOLSETS` and `ENABLED_TOOLS` are both set, a tool must be in both.
- If `TOOLSETS` is not set, version 0.23.1 enables all toolsets.
- `READ_ONLY_MODE=true` removes all write tools.

Thus `ENABLED_TOOLS` gives exactly the subset of tools that the project selects.

## Jira tools (63)

The column "Tokens" gives an estimate of the size of the tool schema (name, description, arguments). The estimate is the number of characters in the source divided by 3.5. The real size depends on the tokenizer of the model. All 63 tools together have approximately 13,000 tokens.

| # | Tool | Toolset | Type | Tokens | Description |
|---|---|---|---|---|---|
| 1 | `jira_get_user_profile` | jira_users | read | 90 | Get the profile of a user. |
| 2 | `jira_search_assignable_users` | jira_users | read | 280 | Find the users that can be assignees in a project or an issue. |
| 3 | `jira_get_issue_watchers` | jira_watchers | read | 60 | List the watchers of an issue. |
| 4 | `jira_add_watcher` | jira_watchers | write | 120 | Add a watcher to an issue. |
| 5 | `jira_remove_watcher` | jira_watchers | write | 150 | Remove a watcher from an issue. |
| 6 | `jira_get_issue` | jira_issues | read | 600 | Get the details of an issue. |
| 7 | `jira_search` | jira_issues | read | 650 | Find issues with JQL. |
| 8 | `jira_search_fields` | jira_fields | read | 170 | Find fields with a keyword. |
| 9 | `jira_get_field_options` | jira_fields | read | 420 | Get the permitted values of a custom field. |
| 10 | `jira_get_project_issues` | jira_issues | read | 150 | Get all issues of a project. |
| 11 | `jira_get_transitions` | jira_transitions | read | 60 | List the status transitions that an issue can do now. |
| 12 | `jira_get_worklog` | jira_worklog | read | 60 | Get the worklogs of an issue. |
| 13 | `jira_download_attachments` | jira_attachments | read | 60 | Download the attachments of an issue. |
| 14 | `jira_get_issue_images` | jira_attachments | read | 80 | Get the images of an issue as inline content. |
| 15 | `jira_get_agile_boards` | jira_agile | read | 260 | Find boards by name, project key or type. |
| 16 | `jira_get_board_issues` | jira_agile | read | 440 | Get the issues of a board with a JQL filter. |
| 17 | `jira_get_sprints_from_board` | jira_agile | read | 200 | Get the sprints of a board by state. |
| 18 | `jira_get_sprint_issues` | jira_agile | read | 220 | Get the issues of a sprint. |
| 19 | `jira_get_link_types` | jira_links | read | 70 | List the types of issue links. |
| 20 | `jira_create_issue` | jira_issues | write | 600 | Create an issue. Optional: epic link or parent for a sub-task. |
| 21 | `jira_batch_create_issues` | jira_issues | write | 260 | Create many issues in one call. |
| 22 | `jira_batch_get_changelogs` | jira_issues | read | 240 | Get the change history of many issues (Cloud only). |
| 23 | `jira_update_issue` | jira_issues | write | 680 | Change the fields of an issue. |
| 24 | `jira_assign_issue` | jira_issues | write | 150 | Set the assignee of an issue. |
| 25 | `jira_delete_issue` | jira_issues | write | 60 | Delete an issue. |
| 26 | `jira_move_issue` | jira_issues | write | 140 | Move an issue to a different project (Cloud only). |
| 27 | `jira_add_comment` | jira_comments | write | 350 | Add a comment to an issue. |
| 28 | `jira_edit_comment` | jira_comments | write | 220 | Change a comment. |
| 29 | `jira_add_worklog` | jira_worklog | write | 360 | Add a worklog to an issue. |
| 30 | `jira_link_to_epic` | jira_links | write | 110 | Link an issue to an epic. |
| 31 | `jira_create_issue_link` | jira_links | write | 380 | Link two issues. |
| 32 | `jira_create_remote_issue_link` | jira_links | write | 350 | Add a web link or a Confluence link to an issue. |
| 33 | `jira_remove_issue_link` | jira_links | write | 60 | Remove a link between two issues. |
| 34 | `jira_transition_issue` | jira_transitions | write | 370 | Change the status of an issue with a transition. |
| 35 | `jira_create_sprint` | jira_agile | write | 240 | Create a sprint on a board. |
| 36 | `jira_update_sprint` | jira_agile | write | 290 | Change a sprint (name, state, dates, goal). |
| 37 | `jira_add_issues_to_sprint` | jira_agile | write | 100 | Put issues into a sprint. |
| 38 | `jira_move_issues_to_backlog` | jira_agile | write | 70 | Move issues to the backlog. |
| 39 | `jira_get_project_issue_types` | jira_projects | read | 60 | List the issue types of a project. |
| 40 | `jira_get_create_fields` | jira_projects | read | 130 | List the fields for the creation of an issue of one type. |
| 41 | `jira_get_project_versions` | jira_projects | read | 60 | List the versions of a project. |
| 42 | `jira_get_project_components` | jira_projects | read | 60 | List the components of a project. |
| 43 | `jira_get_all_projects` | jira_projects | read | 70 | List all projects that the user can see. |
| 44 | `jira_search_projects` | jira_projects | read | 160 | Find projects by name or key. |
| 45 | `jira_get_project_fields` | jira_projects | read | 100 | List the fields of the issues of a project. |
| 46 | `jira_get_service_desk_for_project` | jira_service_desk | read | 60 | Get the service desk of a project. |
| 47 | `jira_get_service_desk_queues` | jira_service_desk | read | 150 | List the queues of a service desk. |
| 48 | `jira_get_queue_issues` | jira_service_desk | read | 190 | Get the issues of a queue. |
| 49 | `jira_get_request_types` | jira_service_desk | read | 160 | List the request types of a service desk. |
| 50 | `jira_get_request_type_fields` | jira_service_desk | read | 110 | Get the fields of a request type. |
| 51 | `jira_create_customer_request` | jira_service_desk | write | 550 | Create a customer request. |
| 52 | `jira_create_version` | jira_projects | write | 240 | Create a version. |
| 53 | `jira_batch_create_versions` | jira_projects | write | 210 | Create many versions in one call. |
| 54 | `jira_update_version` | jira_projects | write | 340 | Change a version. |
| 55 | `jira_get_issue_proforma_forms` | jira_forms | read | 60 | List the forms of an issue. |
| 56 | `jira_get_proforma_form_details` | jira_forms | read | 120 | Get the details of a form. |
| 57 | `jira_update_proforma_form_answers` | jira_forms | write | 180 | Change the answers in a form. |
| 58 | `jira_get_issue_dates` | jira_metrics | read | 180 | Get the dates and the status history of an issue. |
| 59 | `jira_get_issue_sla` | jira_metrics | read | 290 | Calculate the SLA values of an issue. |
| 60 | `jira_get_issue_development_info` | jira_development | read | 230 | Get the pull requests, commits and branches of an issue. |
| 61 | `jira_get_issues_development_info` | jira_development | read | 230 | Get the development data of many issues. |
| 62 | `jira_get_project_epic_hierarchy` | jira_project_analysis | read | 110 | Group the epics of a project under their parent issues. |
| 63 | `jira_get_cross_project_dependencies` | jira_project_analysis | read | 110 | Find the links of a project to other projects. |

## Selection of the tools (proposal)

This section is a proposal. The team must agree on the final list.

### Number of tools

The proposal is **12 tools**, with a maximum of 15. These facts limit the number:

1. **Context**: the tool schemas go into the prompt for each step. Bielik-1.5B has a maximum context of 8192 tokens. The 12 tools below have approximately 4,200 tokens. All 63 tools have approximately 13,000 tokens, and they do not fit.
2. **Selection of a tool**: a small model selects the wrong tool more frequently when the list is long, and when two tools do similar things.
3. **Training data**: each tool needs tasks in the train set and in the test set. More tools need more task categories.
4. **Verification**: each selected tool must change or read a part of the board that the simulator stores and the verifier can check.

### Proposed 12 tools

| # | Tool | Type | Tokens | Reason |
|---|---|---|---|---|
| 1 | `jira_search` | read | 650 | Find issues. The model must write JQL. |
| 2 | `jira_get_issue` | read | 600 | Read one issue with its comments. |
| 3 | `jira_search_assignable_users` | read | 280 | Find the account id of a person from a name. |
| 4 | `jira_get_agile_boards` | read | 260 | Find the board of the project. A sprint belongs to a board. |
| 5 | `jira_get_sprints_from_board` | read | 200 | Find the current sprint and the next sprint. |
| 6 | `jira_get_transitions` | read | 60 | Find the transition id for a new status. |
| 7 | `jira_create_issue` | write | 600 | Create an issue. |
| 8 | `jira_update_issue` | write | 680 | Change the summary, the description, the priority, the labels or the assignee. |
| 9 | `jira_transition_issue` | write | 370 | Change the status. |
| 10 | `jira_add_comment` | write | 350 | Add a comment. |
| 11 | `jira_add_issues_to_sprint` | write | 100 | Put issues into a sprint. |
| 12 | `jira_move_issues_to_backlog` | write | 70 | Move issues to the backlog. |

### Candidates for tools 13 to 15

| Tool | Tokens | Reason |
|---|---|---|
| `jira_create_issue_link` | 380 | Common task: "WEB-5 blokuje WEB-7". It needs `jira_get_link_types` or fixed link names. |
| `jira_link_to_epic` | 110 | Common task: put an issue into an epic. The simulator must have epics. |
| `jira_add_worklog` | 360 | Common task: "zaloguj 2h na WEB-3". |
| `jira_assign_issue` | 150 | It does the same as `assignee` in `jira_update_issue`. Two tools for one operation can confuse the model. |
| `jira_delete_issue` | 60 | A destructive operation. Without this tool, the model must refuse a deletion. |

### Problems for a small model

- `jira_update_issue` takes the argument `fields` as a JSON text, not as an object. The model must write JSON inside JSON.
- `jira_update_issue` returns the full issue by default (`return_fields='*all'`). A large result fills the context. The agent can send `return_fields`.
- `jira_search` needs JQL, for example `project = WEB AND status = "In Progress" AND labels = frontend`.
- A status change needs two calls: `jira_get_transitions`, then `jira_transition_issue`.
- The estimate of the tokens does not include the results of the tools. A multi-step task with search results can need more than the 8192 tokens of Bielik-1.5B.

Measure the exact size of the schemas with the tokenizer of each model before the final decision. The numbers above are estimates.

## How we checked the data

1. Download the sdist 0.23.1 from PyPI.
2. Compare its SHA-256 with the value from PyPI.
3. Parse `src/mcp_atlassian/servers/jira.py` with the Python `ast` module. The code did not run.
4. Find the 63 functions with the decorator `@jira_mcp.tool`. Read their names, tags, arguments and docstrings.
5. Read `servers/main.py`, `utils/toolsets.py` and `docs/configuration.mdx` for the prefix and the filters.

The descriptions in the tables come from the docstrings. We did not start the server, and we did not connect it to a real Jira site. Do this test when the Jira Cloud site exists.

The docstring of `utils/toolsets.py` tells "95 tools". The code has 98 tools (63 Jira and 35 Confluence). The documentation also tells that the default of `TOOLSETS` changes in v0.22.0. The code of 0.23.1 still enables all toolsets by default.
