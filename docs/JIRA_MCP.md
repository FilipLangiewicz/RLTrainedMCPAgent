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

The column "Tokens" gives the size of one tool schema in the prompt of `google/gemma-4-E2B-it`. The measurement uses the chat template of the model. All 63 tools together have 12979 tokens with Gemma 4 and 15708 tokens with `Qwen/Qwen3.5-2B`.

| # | Tool | Toolset | Type | Tokens | Description |
|---|---|---|---|---|---|
| 1 | `jira_get_user_profile` | jira_users | read | 103 | Get the profile of a user. |
| 2 | `jira_search_assignable_users` | jira_users | read | 378 | Find the users that can be assignees in a project or an issue. |
| 3 | `jira_get_issue_watchers` | jira_watchers | read | 83 | List the watchers of an issue. |
| 4 | `jira_add_watcher` | jira_watchers | write | 127 | Add a watcher to an issue. |
| 5 | `jira_remove_watcher` | jira_watchers | write | 126 | Remove a watcher from an issue. |
| 6 | `jira_get_issue` | jira_issues | read | 472 | Get the details of an issue. |
| 7 | `jira_search` | jira_issues | read | 478 | Find issues with JQL. |
| 8 | `jira_search_fields` | jira_fields | read | 112 | Find fields with a keyword. |
| 9 | `jira_get_field_options` | jira_fields | read | 353 | Get the permitted values of a custom field. |
| 10 | `jira_get_project_issues` | jira_issues | read | 129 | Get all issues of a project. |
| 11 | `jira_get_transitions` | jira_transitions | read | 88 | List the status transitions that an issue can do now. |
| 12 | `jira_get_worklog` | jira_worklog | read | 89 | Get the worklogs of an issue. |
| 13 | `jira_download_attachments` | jira_attachments | read | 180 | Download the attachments of an issue. |
| 14 | `jira_get_issue_images` | jira_attachments | read | 183 | Get the images of an issue as inline content. |
| 15 | `jira_get_agile_boards` | jira_agile | read | 190 | Find boards by name, project key or type. |
| 16 | `jira_get_board_issues` | jira_agile | read | 352 | Get the issues of a board with a JQL filter. |
| 17 | `jira_get_sprints_from_board` | jira_agile | read | 157 | Get the sprints of a board by state. |
| 18 | `jira_get_sprint_issues` | jira_agile | read | 173 | Get the issues of a sprint. |
| 19 | `jira_get_link_types` | jira_links | read | 68 | List the types of issue links. |
| 20 | `jira_create_issue` | jira_issues | write | 492 | Create an issue. Optional: epic link or parent for a sub-task. |
| 21 | `jira_batch_create_issues` | jira_issues | write | 246 | Create many issues in one call. |
| 22 | `jira_batch_get_changelogs` | jira_issues | read | 210 | Get the change history of many issues (Cloud only). |
| 23 | `jira_update_issue` | jira_issues | write | 548 | Change the fields of an issue. |
| 24 | `jira_assign_issue` | jira_issues | write | 180 | Set the assignee of an issue. |
| 25 | `jira_delete_issue` | jira_issues | write | 85 | Delete an issue. |
| 26 | `jira_move_issue` | jira_issues | write | 230 | Move an issue to a different project (Cloud only). |
| 27 | `jira_add_comment` | jira_comments | write | 280 | Add a comment to an issue. |
| 28 | `jira_edit_comment` | jira_comments | write | 178 | Change a comment. |
| 29 | `jira_add_worklog` | jira_worklog | write | 299 | Add a worklog to an issue. |
| 30 | `jira_link_to_epic` | jira_links | write | 134 | Link an issue to an epic. |
| 31 | `jira_create_issue_link` | jira_links | write | 319 | Link two issues. |
| 32 | `jira_create_remote_issue_link` | jira_links | write | 313 | Add a web link or a Confluence link to an issue. |
| 33 | `jira_remove_issue_link` | jira_links | write | 70 | Remove a link between two issues. |
| 34 | `jira_transition_issue` | jira_transitions | write | 292 | Change the status of an issue with a transition. |
| 35 | `jira_create_sprint` | jira_agile | write | 195 | Create a sprint on a board. |
| 36 | `jira_update_sprint` | jira_agile | write | 194 | Change a sprint (name, state, dates, goal). |
| 37 | `jira_add_issues_to_sprint` | jira_agile | write | 115 | Put issues into a sprint. |
| 38 | `jira_move_issues_to_backlog` | jira_agile | write | 91 | Move issues to the backlog. |
| 39 | `jira_get_project_issue_types` | jira_projects | read | 132 | List the issue types of a project. |
| 40 | `jira_get_create_fields` | jira_projects | read | 188 | List the fields for the creation of an issue of one type. |
| 41 | `jira_get_project_versions` | jira_projects | read | 83 | List the versions of a project. |
| 42 | `jira_get_project_components` | jira_projects | read | 82 | List the components of a project. |
| 43 | `jira_get_all_projects` | jira_projects | read | 67 | List all projects that the user can see. |
| 44 | `jira_search_projects` | jira_projects | read | 139 | Find projects by name or key. |
| 45 | `jira_get_project_fields` | jira_projects | read | 113 | List the fields of the issues of a project. |
| 46 | `jira_get_service_desk_for_project` | jira_service_desk | read | 95 | Get the service desk of a project. |
| 47 | `jira_get_service_desk_queues` | jira_service_desk | read | 141 | List the queues of a service desk. |
| 48 | `jira_get_queue_issues` | jira_service_desk | read | 171 | Get the issues of a queue. |
| 49 | `jira_get_request_types` | jira_service_desk | read | 128 | List the request types of a service desk. |
| 50 | `jira_get_request_type_fields` | jira_service_desk | read | 120 | Get the fields of a request type. |
| 51 | `jira_create_customer_request` | jira_service_desk | write | 436 | Create a customer request. |
| 52 | `jira_create_version` | jira_projects | write | 167 | Create a version. |
| 53 | `jira_batch_create_versions` | jira_projects | write | 227 | Create many versions in one call. |
| 54 | `jira_update_version` | jira_projects | write | 253 | Change a version. |
| 55 | `jira_get_issue_proforma_forms` | jira_forms | read | 104 | List the forms of an issue. |
| 56 | `jira_get_proforma_form_details` | jira_forms | read | 168 | Get the details of a form. |
| 57 | `jira_update_proforma_form_answers` | jira_forms | write | 802 | Change the answers in a form. |
| 58 | `jira_get_issue_dates` | jira_metrics | read | 171 | Get the dates and the status history of an issue. |
| 59 | `jira_get_issue_sla` | jira_metrics | read | 419 | Calculate the SLA values of an issue. |
| 60 | `jira_get_issue_development_info` | jira_development | read | 225 | Get the pull requests, commits and branches of an issue. |
| 61 | `jira_get_issues_development_info` | jira_development | read | 215 | Get the development data of many issues. |
| 62 | `jira_get_project_epic_hierarchy` | jira_project_analysis | read | 178 | Group the epics of a project under their parent issues. |
| 63 | `jira_get_cross_project_dependencies` | jira_project_analysis | read | 153 | Find the links of a project to other projects. |

## Selected tools

The project uses 13 of the 63 Jira tools. `docs/JIRA_TOOLS.md` gives their contracts. `data/mcp_atlassian_tools.json` has their exact schemas.

```text
jira_search,jira_get_issue,jira_search_assignable_users,jira_get_agile_boards,jira_get_sprints_from_board,jira_get_transitions,jira_create_issue,jira_update_issue,jira_transition_issue,jira_add_comment,jira_add_worklog,jira_add_issues_to_sprint,jira_move_issues_to_backlog
```

These facts limit the number of tools:

1. **Context**: the tool schemas go into the prompt for each step. The 13 tools have 3820 tokens (Gemma 4) or 4679 tokens (Qwen3.5). Bielik-1.5B has a maximum context of 8192 tokens.
2. **Selection of a tool**: a small model selects the wrong tool more frequently when the list is long, and when two tools do similar things.
3. **Training data**: each tool needs tasks in the train set and in the test set.

## Make a Jira Cloud site

The goal is a free Jira site for a test of the model on real Jira.

1. Open https://www.atlassian.com/software/jira/free and sign up with an e-mail address.
2. Select the Free plan. The plan is free for up to 10 users.
3. Give the site a name. The site address is `https://<name>.atlassian.net`.
4. Create a project with the template "Scrum". A Scrum project has a board and sprints.
5. Write down the project key, for example `WEB`.

## Make an API token

The goal is a token for the Jira REST API.

1. Open https://id.atlassian.com/manage-profile/security/api-tokens.
2. Click **Create API token**. Do not select scopes.
3. Give the token a name and an expiry date. The maximum expiry is 365 days.
4. Copy the token. Atlassian shows it only one time.
5. Put the values into `.env` in the root folder of the repository:

   ```bash
   JIRA_URL=https://<name>.atlassian.net
   JIRA_USERNAME=<your e-mail address>
   JIRA_API_TOKEN=<your token>
   ```

Never commit `.env`. A token with scopes needs the URL `https://api.atlassian.com/ex/jira/<cloudId>`, so this procedure uses a token without scopes.

Source: https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/

## Start the server

The goal is a server with only the 13 selected tools. Do these steps in the root folder of the repository:

1. Install uv (see `AGENTS.md`).
2. Start the server:

   ```bash
   uvx mcp-atlassian==0.23.1 --env-file .env --toolsets all --enabled-tools "jira_search,jira_get_issue,jira_search_assignable_users,jira_get_agile_boards,jira_get_sprints_from_board,jira_get_transitions,jira_create_issue,jira_update_issue,jira_transition_issue,jira_add_comment,jira_add_worklog,jira_add_issues_to_sprint,jira_move_issues_to_backlog"
   ```

`uvx` runs the server in a separate environment. Thus the server does not change `.venv`. The server uses `mcp` 1.x, and `.venv` has `mcp` 2.x.

## Record the schemas again

The goal is a new copy of `data/mcp_atlassian_tools.json`, for example after a change of the version. The server does not need a Jira site for the list of tools.

1. Make a separate environment: `uv venv --python 3.13 <folder>`.
2. Install the server: `uv pip install --python <folder> mcp-atlassian==0.23.1`.
3. Set `JIRA_URL`, `JIRA_USERNAME` and `JIRA_API_TOKEN` to any values, and set `TOOLSETS=all`.
4. Connect `fastmcp.Client` to `mcp_atlassian.servers.main.main_mcp` in the same process and call `list_tools()`.
5. Save `name`, `description`, `inputSchema` and `annotations` of the 13 selected tools in the same order.

## How we checked the data

1. Download the sdist 0.23.1 from PyPI. Compare its SHA-256 with the value from PyPI.
2. Read `src/mcp_atlassian/servers/jira.py`, `jira/issues.py`, `servers/main.py` and `utils/toolsets.py`.
3. Install 0.23.1 in a separate environment (`fastmcp` 3.4.11, `mcp` 1.30.0). Call `list_tools()` on the server with dummy credentials. The result has 63 Jira tools.
4. Save the schemas of the 13 selected tools in `data/mcp_atlassian_tools.json`.
5. Count the tokens of the schemas with the chat templates of `Qwen/Qwen3.5-2B` and `google/gemma-4-E2B-it`.

We did not connect the server to a real Jira site. Do this test when the Jira Cloud site exists. Also record real results of the 13 tools. The simulator must copy their format.

The code shows these facts:

- `jira_update_issue` with `{"status": ...}` in `fields` does a transition. The project uses `jira_transition_issue` for a status change (see `docs/JIRA_TOOLS.md`).
- `assignee` accepts an e-mail, a display name or an account id. The server finds the account id.
- `labels` in `fields` replaces the full list of labels.
- The docstring of `utils/toolsets.py` tells "95 tools". The code has 98 tools (63 Jira and 35 Confluence).
- The documentation tells that the default of `TOOLSETS` changes in v0.22.0. The code of 0.23.1 still enables all toolsets by default.
