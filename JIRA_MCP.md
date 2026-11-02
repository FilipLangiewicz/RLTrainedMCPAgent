# Jira MCP servers

This file describes the real MCP servers for Jira. It compares them with the tools of our simulator. Date of the research: 2026-11-02.

## Summary

- Our project does not use a real Jira MCP server. `src/tools.py` is our own MCP server with 7 tools. It operates on the simulator board (`src/environment.py`).
- We designed the 7 tools ourselves in the OpenSpec change `e1-base-system`. We did not copy them from a real server. The names and arguments are simpler than in real Jira.
- Two real MCP servers for Jira exist:
  1. **Atlassian Rovo MCP Server**: the official remote server of Atlassian. It has 52 Jira tools.
  2. **mcp-atlassian** (sooperset): a popular community server in Python. It has 63 Jira tools.
- Our 7 tools are a small subset of the functions of real Jira. They cover issues, persons, sprints and comments. They do not cover transitions, JQL, epics, links, worklogs, versions, attachments and other areas.
- For E3 (real Jira), an adapter must map our 7 tools to the tools of one real server. See "Differences that the adapter must solve".

## Our MCP server (the simulator)

Source: `src/tools.py`. Library: `mcp` 2.3.0 (`mcp.server.mcpserver.MCPServer`). Spec: `openspec/specs/environment-tools/spec.md`.

| # | Tool | Type | Description |
|---|---|---|---|
| 1 | `list_users` | read | List all persons with their id and display name. |
| 2 | `list_sprints` | read | List all sprints with their id, name and state (`closed`, `active`, `future`). |
| 3 | `search_issues` | read | Find issues with optional filters: status, assignee, label, type, priority, sprint, text. Returns at most 50 issues. |
| 4 | `get_issue` | read | Get all fields of one issue, with its comments. |
| 5 | `create_issue` | write | Create an issue with a title and a type. Optional: description, priority, assignee, labels, sprint. |
| 6 | `update_issue` | write | Change one or more fields: title, description, type, status, priority, assignee, sprint, labels. |
| 7 | `add_comment` | write | Add a comment to an issue. |

The simulator has these values:

- Issue types: `bug`, `task`, `story`.
- Statuses: `to_do`, `in_progress`, `done`.
- Priorities: `low`, `medium`, `high`, `critical`.

## Server 1: Atlassian Rovo MCP Server (official)

| Property | Value |
|---|---|
| Owner | Atlassian |
| Type | Remote server (hosted by Atlassian). There is no code to download. |
| Version | MCP v2. The changelog has no version numbers, only dates. The last entry is 2026-11-02. |
| Endpoint | `https://mcp.atlassian.com/v2/mcp` |
| Endpoint with all tools | `https://mcp.atlassian.com/v2/mcp?tools=all` |
| Old endpoint | `https://mcp.atlassian.com/v1/mcp`. On 2027-03-01, v1 starts to use the v2 tools automatically. |
| Authentication | OAuth 2.1. An API token is also possible if an admin enables it. |
| Products | Jira, Jira Service Management, Confluence, Jira Align, Bitbucket, Loom, Teamwork Graph and others. |
| Cost | Each tool call uses Rovo credits. The limit depends on the plan. |

Sources:

- Supported tools: https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/
- Supported tools (support site): https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/
- Changelog: https://developer.atlassian.com/cloud/rovo-mcp/changelog/
- Start guide: https://support.atlassian.com/atlassian-ai-gateway/docs/get-started-with-the-atlassian-remote-mcp-server/
- Upgrade from v1 to v2: https://support.atlassian.com/atlassian-ai-gateway/docs/how-to-upgrade-from-atlassian-mcp-v1-to-atlassian-mcp-v2/

### How the tool list operates

- By default, `tools/list` returns only a small set of "primary" tools.
- The model finds other tools with the tool `discover`. Then it calls them with `executeRead`, `executeWrite` or `executeDestructive`.
- With `?tools=all`, the server returns all tools in one flat list, without `discover`.
- An admin enables the permission groups. The groups `delete_jira` and `manage_jira` are disabled by default.
- The new Atlassian user interface uses "work item" for "issue" and "space" for "project". The tool names still use "Issue" and "Project".

### General tools

| # | Tool | Description |
|---|---|---|
| 1 | `atlassianUserInfo` | Get the account data of the current user. |
| 2 | `getAccessibleAtlassianResources` | List the sites and their `cloudId`. Each other tool call needs a `cloudId`, so this call is first. |
| 3 | `discover` | Find a tool in the catalog with a text in natural language. |
| 4 | `executeRead` | Run a read tool from the catalog. |
| 5 | `executeWrite` | Run a write tool from the catalog. |
| 6 | `executeDestructive` | Run a destructive tool from the catalog. |
| 7 | `getContentFormatGuide` | Get the rules for the format of rich text. |
| 8 | `search` (beta) | Semantic search in Jira, Confluence and connected apps. |

### Jira tools (52)

"P" marks a primary tool. A primary tool is in the default `tools/list`.

| # | Tool | Group | Description |
|---|---|---|---|
| 1 | `getJiraIssue` (P) | read_jira | Get an issue by id or key. |
| 2 | `listJiraProjects` | read_jira | List the projects that the user can see. |
| 3 | `listJiraProjectIssueTypesMetadata` | read_jira | List the issue types of a project. |
| 4 | `getJiraIssueTypeMetaWithFields` | read_jira | Get the fields of one issue type. |
| 5 | `listJiraIssueTransitions` | read_jira | List the workflow transitions that an issue can do now. |
| 6 | `listJiraIssueLinkTypes` | read_jira | List the types of issue links. |
| 7 | `listJiraIssueRemoteIssueLinks` | read_jira | List the remote links of an issue. |
| 8 | `listJiraIssueWorklogs` | read_jira | List the worklogs of an issue. |
| 9 | `lookupJiraAccountId` | read_jira | Find an account id from a display name or an e-mail. |
| 10 | `listJiraIssueAssignableUsers` | read_jira | List the users that can be assignees in a project or an issue. |
| 11 | `listJiraIssueComments` (P) | read_jira | List the comments of an issue. |
| 12 | `listJiraIssueChangelogs` | read_jira | Get the history of the field changes of an issue. |
| 13 | `getJiraCurrentUser` | read_jira | Get the data of the current Jira user. |
| 14 | `getJiraUser` | read_jira | Get a user profile from an account id. |
| 15 | `listJiraStatuses` | read_jira | List all possible statuses. |
| 16 | `listJiraProjectComponents` | read_jira | List the components of a project. |
| 17 | `getJiraProjectVersions` | read_jira | Get the versions (releases) of a project. |
| 18 | `getJiraProjectVersionRelatedWork` | read_jira | Get the related work links of a version. |
| 19 | `listJiraBoards` | read_jira | List the boards that the user can see. |
| 20 | `getJiraBoardConfig` | read_jira | Get the filter, the columns and the status mapping of a board. |
| 21 | `getJiraBoardIssueData` | read_jira | Get the issues of a board, with an optional filter. |
| 22 | `getJiraBoardSprintData` | read_jira | Get the data of a board and its sprint (the active sprint by default). |
| 23 | `listJiraBoardSprints` | read_jira | List the sprints of a board, with a filter for active, future or closed. |
| 24 | `listJiraFilters` | read_jira | List the saved filters with their JQL. |
| 25 | `listJiraDashboards` | read_jira | List the dashboards. |
| 26 | `getJiraEntityProperty` | read_jira | Read a key/value property of an issue, comment, worklog, dashboard item or user. |
| 27 | `downloadJiraIssueAttachment` | read_jira | Get a temporary download URL of an attachment. |
| 28 | `createJiraIssue` (P) | write_jira | Create an issue. |
| 29 | `editJiraIssue` (P) | write_jira | Change the editable fields of an issue. |
| 30 | `transitionJiraIssue` (P) | write_jira | Change the status with a transition, or move the issue to a sprint or to the backlog. |
| 31 | `addOrEditJiraIssueComment` (P) | write_jira | Add a comment or change a comment. |
| 32 | `addOrEditJiraIssueWorklog` | write_jira | Log time or change a worklog. |
| 33 | `createJiraIssueLink` | write_jira | Link two issues. |
| 34 | `manageJiraProjectVersion` | write_jira | Create, update, release or archive a version. |
| 35 | `manageJiraProjectVersionRelatedWork` | write_jira | Create or update the related work links of a version. |
| 36 | `manageJiraSprint` | write_jira | Create, fill, start, update or close a sprint. |
| 37 | `createJiraBoard` | write_jira | Create a scrum or kanban board from a filter. |
| 38 | `watchJiraIssue` | write_jira | Start or stop to watch an issue. |
| 39 | `uploadAttachmentToJiraIssue` | write_jira | Attach a local file to an issue. |
| 40 | `editJiraEntityProperty` | write_jira | Set a key/value property of an entity. |
| 41 | `createJiraIssueRemoteIssueLink` | write_jira | Add a web link or a Confluence link to an issue. |
| 42 | `convertJiraIssueHierarchy` | write_jira | Change a sub-task to a standard issue, or the opposite. |
| 43 | `searchJiraIssuesUsingJql` (P) | search_jira | Find issues with JQL. |
| 44 | `deleteJiraIssue` | delete_jira | Delete an issue permanently. |
| 45 | `deleteJiraComment` | delete_jira | Delete a comment permanently. |
| 46 | `deleteJiraIssueAttachment` | delete_jira | Delete an attachment permanently. |
| 47 | `createJiraProject` | manage_jira | Create a project from a template. |
| 48 | `updateJiraProject` | manage_jira | Change the settings of a project. |
| 49 | `getJiraWorkflows` | manage_jira | Read the workflows, statuses and transitions of a project. |
| 50 | `getJiraWorkflowEditorLink` | manage_jira | Get a link to the workflow editor. The tool does not apply a change. |
| 51 | `getJiraScreen` | manage_jira | Read a Create, View or Edit screen. |
| 52 | `updateJiraScreen` | manage_jira | Add or move fields on a screen. |

The server also has 16 Jira Service Management tools (`read_jsm`, `write_jsm`) and 64 Confluence tools. This file does not list them, because our project does not use them.

## Server 2: mcp-atlassian (community)

| Property | Value |
|---|---|
| Owner | sooperset (Hyeonsoo Lee), community project. Atlassian does not support it. |
| Repository | https://github.com/sooperset/mcp-atlassian |
| Package | https://pypi.org/project/mcp-atlassian/ |
| Version | 0.23.1 (PyPI, 2026-08-19). This is the last version on PyPI on 2026-11-02. |
| SHA-256 of the sdist | `6b57391928887f5334fe854073b09e3a49bb7dae0d55a1b1276f4d910607a0f1` |
| License | MIT |
| Language | Python 3.10 or newer. It uses `fastmcp` 3.x and `mcp` 1.x. |
| Type | Local server (`uvx mcp-atlassian` or Docker). Transports: stdio, SSE, streamable HTTP. |
| Jira versions | Jira Cloud (`JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`) and Jira Server/Data Center (`JIRA_PERSONAL_TOKEN`). |
| Tools | 63 Jira tools in 16 toolsets, and 35 Confluence tools. |

### How the tool list operates

- The server adds the prefix `jira_` to each Jira tool, for example `jira_get_issue` (`main_mcp.mount(jira_mcp, namespace="jira")`).
- `TOOLSETS` selects groups of tools. `TOOLSETS=default` gives 4 Jira toolsets: `jira_issues`, `jira_fields`, `jira_comments`, `jira_transitions`.
- If `TOOLSETS` is not set, version 0.23.1 enables all toolsets. The documentation tells that this default changes in v0.22.0, but the code of 0.23.1 does not do this.
- `ENABLED_TOOLS` gives a list of tool names. `READ_ONLY_MODE=true` removes all write tools.

### Jira tools (63)

| # | Tool | Toolset | Type | Description |
|---|---|---|---|---|
| 1 | `jira_get_user_profile` | jira_users | read | Get the profile of a user. |
| 2 | `jira_search_assignable_users` | jira_users | read | Find the users that can be assignees in a project or an issue. |
| 3 | `jira_get_issue_watchers` | jira_watchers | read | List the watchers of an issue. |
| 4 | `jira_add_watcher` | jira_watchers | write | Add a watcher to an issue. |
| 5 | `jira_remove_watcher` | jira_watchers | write | Remove a watcher from an issue. |
| 6 | `jira_get_issue` | jira_issues | read | Get the details of an issue. |
| 7 | `jira_search` | jira_issues | read | Find issues with JQL. |
| 8 | `jira_search_fields` | jira_fields | read | Find fields with a keyword. |
| 9 | `jira_get_field_options` | jira_fields | read | Get the permitted values of a custom field. |
| 10 | `jira_get_project_issues` | jira_issues | read | Get all issues of a project. |
| 11 | `jira_get_transitions` | jira_transitions | read | List the status transitions that an issue can do now. |
| 12 | `jira_get_worklog` | jira_worklog | read | Get the worklogs of an issue. |
| 13 | `jira_download_attachments` | jira_attachments | read | Download the attachments of an issue. |
| 14 | `jira_get_issue_images` | jira_attachments | read | Get the images of an issue as inline content. |
| 15 | `jira_get_agile_boards` | jira_agile | read | Find boards by name, project key or type. |
| 16 | `jira_get_board_issues` | jira_agile | read | Get the issues of a board with a JQL filter. |
| 17 | `jira_get_sprints_from_board` | jira_agile | read | Get the sprints of a board by state. |
| 18 | `jira_get_sprint_issues` | jira_agile | read | Get the issues of a sprint. |
| 19 | `jira_get_link_types` | jira_links | read | List the types of issue links. |
| 20 | `jira_create_issue` | jira_issues | write | Create an issue. Optional: epic link or parent for a sub-task. |
| 21 | `jira_batch_create_issues` | jira_issues | write | Create many issues in one call. |
| 22 | `jira_batch_get_changelogs` | jira_issues | read | Get the change history of many issues (Cloud only). |
| 23 | `jira_update_issue` | jira_issues | write | Change the fields of an issue. |
| 24 | `jira_assign_issue` | jira_issues | write | Set the assignee of an issue. |
| 25 | `jira_delete_issue` | jira_issues | write | Delete an issue. |
| 26 | `jira_move_issue` | jira_issues | write | Move an issue to a different project (Cloud only). |
| 27 | `jira_add_comment` | jira_comments | write | Add a comment to an issue. |
| 28 | `jira_edit_comment` | jira_comments | write | Change a comment. |
| 29 | `jira_add_worklog` | jira_worklog | write | Add a worklog to an issue. |
| 30 | `jira_link_to_epic` | jira_links | write | Link an issue to an epic. |
| 31 | `jira_create_issue_link` | jira_links | write | Link two issues. |
| 32 | `jira_create_remote_issue_link` | jira_links | write | Add a web link or a Confluence link to an issue. |
| 33 | `jira_remove_issue_link` | jira_links | write | Remove a link between two issues. |
| 34 | `jira_transition_issue` | jira_transitions | write | Change the status of an issue with a transition. |
| 35 | `jira_create_sprint` | jira_agile | write | Create a sprint on a board. |
| 36 | `jira_update_sprint` | jira_agile | write | Change a sprint (name, state, dates, goal). |
| 37 | `jira_add_issues_to_sprint` | jira_agile | write | Put issues into a sprint. |
| 38 | `jira_move_issues_to_backlog` | jira_agile | write | Move issues to the backlog. |
| 39 | `jira_get_project_issue_types` | jira_projects | read | List the issue types of a project. |
| 40 | `jira_get_create_fields` | jira_projects | read | List the fields for the creation of an issue of one type. |
| 41 | `jira_get_project_versions` | jira_projects | read | List the versions of a project. |
| 42 | `jira_get_project_components` | jira_projects | read | List the components of a project. |
| 43 | `jira_get_all_projects` | jira_projects | read | List all projects that the user can see. |
| 44 | `jira_search_projects` | jira_projects | read | Find projects by name or key. |
| 45 | `jira_get_project_fields` | jira_projects | read | List the fields of the issues of a project. |
| 46 | `jira_get_service_desk_for_project` | jira_service_desk | read | Get the service desk of a project. |
| 47 | `jira_get_service_desk_queues` | jira_service_desk | read | List the queues of a service desk. |
| 48 | `jira_get_queue_issues` | jira_service_desk | read | Get the issues of a queue. |
| 49 | `jira_get_request_types` | jira_service_desk | read | List the request types of a service desk. |
| 50 | `jira_get_request_type_fields` | jira_service_desk | read | Get the fields of a request type. |
| 51 | `jira_create_customer_request` | jira_service_desk | write | Create a customer request. |
| 52 | `jira_create_version` | jira_projects | write | Create a version. |
| 53 | `jira_batch_create_versions` | jira_projects | write | Create many versions in one call. |
| 54 | `jira_update_version` | jira_projects | write | Change a version. |
| 55 | `jira_get_issue_proforma_forms` | jira_forms | read | List the forms of an issue. |
| 56 | `jira_get_proforma_form_details` | jira_forms | read | Get the details of a form. |
| 57 | `jira_update_proforma_form_answers` | jira_forms | write | Change the answers in a form. |
| 58 | `jira_get_issue_dates` | jira_metrics | read | Get the dates and the status history of an issue. |
| 59 | `jira_get_issue_sla` | jira_metrics | read | Calculate the SLA values of an issue. |
| 60 | `jira_get_issue_development_info` | jira_development | read | Get the pull requests, commits and branches of an issue. |
| 61 | `jira_get_issues_development_info` | jira_development | read | Get the development data of many issues. |
| 62 | `jira_get_project_epic_hierarchy` | jira_project_analysis | read | Group the epics of a project under their parent issues. |
| 63 | `jira_get_cross_project_dependencies` | jira_project_analysis | read | Find the links of a project to other projects. |

## How we checked the data

- **mcp-atlassian**: we downloaded the sdist 0.23.1 from PyPI and checked its SHA-256. A script parsed `servers/jira.py` with the Python `ast` module. It found 63 functions with the decorator `@jira_mcp.tool` and read their names, tags and docstrings. The descriptions in the table come from the docstrings. We did not start the server. A start needs an installation and a Jira account.
- **Rovo MCP Server**: the data comes from the documentation pages of Atlassian (see the sources). The server is remote, so there is no code to check. We did not connect to it, because a connection needs an Atlassian account and OAuth.
- Do this check again before E3. The Rovo changelog shows changes each week.

Some facts in the sources do not agree:

- The docstring of `utils/toolsets.py` in mcp-atlassian tells "95 tools". The code has 98 tools (63 Jira and 35 Confluence).
- The two Rovo pages do not agree on some tools outside Jira, and on the "primary" mark of `listJiraIssueComments`.

## The subset that our project uses

The table maps each simulator tool to the tools of the real servers.

| # | Simulator tool | Rovo MCP Server | mcp-atlassian |
|---|---|---|---|
| 1 | `list_users` | `listJiraIssueAssignableUsers`, `lookupJiraAccountId` | `jira_search_assignable_users`, `jira_get_user_profile` |
| 2 | `list_sprints` | `listJiraBoards` and `listJiraBoardSprints` | `jira_get_agile_boards` and `jira_get_sprints_from_board` |
| 3 | `search_issues` | `searchJiraIssuesUsingJql` | `jira_search` |
| 4 | `get_issue` | `getJiraIssue` and `listJiraIssueComments` | `jira_get_issue` |
| 5 | `create_issue` | `createJiraIssue`, then `transitionJiraIssue` for the sprint | `jira_create_issue`, then `jira_add_issues_to_sprint` |
| 6 | `update_issue` | `editJiraIssue` and `transitionJiraIssue` | `jira_update_issue`, `jira_assign_issue`, `jira_transition_issue`, `jira_add_issues_to_sprint`, `jira_move_issues_to_backlog` |
| 7 | `add_comment` | `addOrEditJiraIssueComment` | `jira_add_comment` |

Thus our 7 tools need 11 of the 52 Rovo Jira tools, or 13 of the 63 mcp-atlassian Jira tools. The status change needs one more tool for the list of transitions (see below).

The simulator does not have these Jira areas:

- workflow transitions (the simulator sets the status directly)
- JQL (the simulator has fixed filters)
- epics, sub-tasks and issue links
- worklogs, attachments and watchers
- versions, components, boards and filters
- the creation, start and close of a sprint
- the deletion of an issue or a comment (the `refusal` tasks expect a refusal for a deletion)
- custom fields, forms and Jira Service Management

### Differences that the adapter must solve

1. **Status**: real Jira changes a status with a transition. The adapter must find the transition id first (`listJiraIssueTransitions` or `jira_get_transitions`).
2. **Search**: real Jira uses JQL. The adapter must change the filters of `search_issues` into a JQL text, for example `status = "In Progress" AND labels = frontend`.
3. **Persons**: real Jira uses an account id, not `u1` to `u6`.
4. **Sprints**: a sprint belongs to a board. The adapter must find the board id first.
5. **Values**: the names of the statuses, types and priorities are different. The default priorities of Jira are Highest, High, Medium, Low and Lowest. The simulator has `critical`, `high`, `medium` and `low`.
6. **Site**: each Rovo tool call needs a `cloudId` from `getAccessibleAtlassianResources`.
7. **Cost**: each Rovo tool call uses Rovo credits. mcp-atlassian calls the Jira REST API directly and does not use credits.

## Open decision for E3

The team must select one server for the test on real Jira (free cloud plan):

- **Rovo MCP Server**: the official server. It needs OAuth or an API token that an admin enables. Each call uses Rovo credits. The tool set changes often.
- **mcp-atlassian**: a local server with a fixed version (0.23.1). It needs an API token only. We can lock its version, and the tool set does not change between runs.
