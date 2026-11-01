# environment-tools Specification

## Purpose

The environment tools give the operations of one environment to a model through an MCP server. The tool contract is the interface that the agent, the training and a later adapter to a real system use.

## Requirements

### Requirement: Tool list
The MCP server SHALL give these seven tools for one board: `list_users`, `list_sprints`, `search_issues`, `get_issue`, `create_issue`, `update_issue`, `add_comment`. Each tool SHALL have a description and a JSON schema of its arguments.

#### Scenario: List of tools
- **WHEN** an MCP client asks the server for its tools
- **THEN** the client gets the seven tools, each with a description and an argument schema

### Requirement: Read tools
`list_users` SHALL return the id and the display name of each person. `list_sprints` SHALL return the id, the name and the state of each sprint. `search_issues` SHALL take the filters of the environment search as optional arguments and return a short form of each found issue: key, title, type, status, priority, assignee, labels, sprint. `get_issue` SHALL return all fields of one issue, with its comments.

#### Scenario: Search without filters
- **WHEN** the model calls `search_issues` without arguments
- **THEN** the tool returns the short form of all issues of the board

#### Scenario: Full issue
- **WHEN** the model calls `get_issue` with the key `WEB-7`
- **THEN** the tool returns all fields and comments of `WEB-7`

### Requirement: Write tools
`create_issue` SHALL take a title and a type, and optionally a description, a priority, an assignee, labels and a sprint. It SHALL return the key of the new issue. `update_issue` SHALL take a key and one or more of: title, description, type, status, priority, assignee, sprint, labels to add, labels to remove. `add_comment` SHALL take a key and a text. An assignee or a sprint argument SHALL accept the value `none` to clear the field.

#### Scenario: Two fields in one call
- **WHEN** the model calls `update_issue` with the key `WEB-3`, the status `in_progress` and the assignee `u2`
- **THEN** both fields of `WEB-3` change
- **AND** the tool returns the updated short form of `WEB-3`

#### Scenario: Move to backlog
- **WHEN** the model calls `update_issue` with the key `WEB-3` and the sprint `none`
- **THEN** `WEB-3` has no sprint

### Requirement: Tool errors
A tool call with a wrong argument SHALL return an MCP error result with a message that tells the model the cause. The error SHALL not stop the server. The board SHALL not change after a failed call.

#### Scenario: Unknown key
- **WHEN** the model calls `get_issue` with a key that does not exist
- **THEN** the result is an error with a message that names the key
- **AND** the next tool call operates normally

### Requirement: One board for each server
Each server instance SHALL operate on one board that the caller gives. Two server instances SHALL not share a board.

#### Scenario: Separate tasks
- **WHEN** the agent does two tasks with two server instances
- **THEN** a change in the first task does not occur on the board of the second task

### Requirement: Stand-alone server
The MCP server SHALL also start as a stand-alone process with the stdio transport and a board file as an argument.

#### Scenario: Start from the command line
- **WHEN** a user starts the server with a board file
- **THEN** an external MCP client can connect over stdio and list the tools
