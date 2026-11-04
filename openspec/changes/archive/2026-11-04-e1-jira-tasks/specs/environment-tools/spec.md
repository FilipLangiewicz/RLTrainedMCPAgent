## MODIFIED Requirements

### Requirement: Tool list
The MCP server SHALL give the 14 tools of `data/mcp_atlassian_tools.json` for one board. Each tool SHALL have the same name, description and argument schema as in this file, without a change. The server SHALL give no other tools.

#### Scenario: List of tools
- **WHEN** an MCP client asks the server for its tools
- **THEN** the client gets 14 tools
- **AND** the name, the description and the argument schema of each tool are equal to the values in `data/mcp_atlassian_tools.json`

### Requirement: Read tools
The read tools SHALL return the keys and the formats of the real server in `data/jira_recorded_results.json`: the search, one issue with its comments, the assignable persons, the agile boards, the sprints of a board, the transitions of an issue and the worklogs of an issue. A read tool SHALL not change the board.

#### Scenario: Search without filters
- **WHEN** the model searches with `project = WEB` and a limit of 10
- **THEN** the result has the keys `total`, `start_at`, `max_results` and `issues`
- **AND** `total` is `-1` and `issues` has 10 issues

#### Scenario: Full issue
- **WHEN** the model reads the issue `WEB-6` with the argument `comment_limit`
- **THEN** the result has the fields of the issue and its comments
- **AND** an issue without an assignee has `"assignee": {"display_name": "Unassigned"}`

#### Scenario: Transitions
- **WHEN** the model asks for the transitions of an issue
- **THEN** the result is a list of five objects with a number `id` and a `name`

#### Scenario: Assignable persons
- **WHEN** the model searches the assignable persons with the query `Ann`
- **THEN** the result has each active person with a word of the display name that starts with "Ann"

### Requirement: Write tools
The write tools SHALL create an issue, change the fields of an issue (the `fields` argument is a JSON text), do a transition, add a comment, add a worklog, put issues into a sprint and move issues to the backlog. A list of keys SHALL be one text with commas. Each write tool SHALL return the message and the keys of the real server.

#### Scenario: Two fields in one call
- **WHEN** the model changes `WEB-7` with `{"assignee": "Ewa Mazur", "priority": {"name": "Highest"}}`
- **THEN** both fields of `WEB-7` change
- **AND** the result starts with the message "Issue updated successfully"

#### Scenario: Move to backlog
- **WHEN** the model moves `"WEB-14"` to the backlog
- **THEN** `WEB-14` has no sprint
- **AND** the result is "Successfully moved 1 issue(s) to backlog"

#### Scenario: Labels replace the old list
- **WHEN** the model changes the issue `WEB-14` with `{"labels": ["frontend"]}` and `WEB-14` had the label `ui`
- **THEN** `WEB-14` has only the label `frontend`

#### Scenario: Two issues to a sprint
- **WHEN** the model puts `"WEB-1,WEB-2"` into the sprint `42`
- **THEN** both issues are in the sprint `42`
- **AND** the result is "Successfully added 2 issue(s) to sprint"

### Requirement: Tool errors
A tool call with a wrong argument SHALL return an MCP error result with the message of the real server. The error SHALL not stop the server. The board SHALL not change after a failed call.

#### Scenario: Unknown key
- **WHEN** the model reads the issue `WEB-999` and it does not exist
- **THEN** the result is the error "Issue WEB-999 not found. Verify the issue key and project access."
- **AND** the next tool call operates normally

#### Scenario: Search without a condition
- **WHEN** the model searches with `ORDER BY created DESC`
- **THEN** the result is the error "Unbounded JQL queries are not allowed here. Please add a search restriction to your query."

## ADDED Requirements

### Requirement: Person in a change
A person in the `assignee` argument SHALL be a full display name, an e-mail or an account id. The comparison of a name or an e-mail SHALL ignore case and Polish letters. A first name only, a part of a name or a person who is not active SHALL give an error in the update tool.

#### Scenario: Name without Polish letters
- **WHEN** the model changes an issue with `{"assignee": "lukasz ostrowski"}` and the board has the person Łukasz Ostrowski
- **THEN** the assignee of the issue is Łukasz Ostrowski

#### Scenario: First name only
- **WHEN** the model changes an issue with `{"assignee": "Ewa"}`
- **THEN** the result is an error that contains "Could not find account ID for user: Ewa"
- **AND** the board does not change

### Requirement: Hidden errors of real Jira
The tools SHALL copy the errors that the real server does not show. The create tool with an unknown assignee SHALL create the issue without an assignee and report success. The worklog tool with a time that it cannot read SHALL log one minute and report success.

#### Scenario: Unknown assignee in a new issue
- **WHEN** the model creates an issue with the assignee "Ewa"
- **THEN** the result is "Issue created successfully"
- **AND** the new issue has no assignee

#### Scenario: Time in words
- **WHEN** the model adds a worklog with the time "półtorej godziny"
- **THEN** the result is "Worklog added successfully"
- **AND** the worklog has 60 seconds

### Requirement: Contract test
A test SHALL run the calls of `data/jira_recorded_results.json` on a board with the content of the Jira Cloud site at the time of the recording. For each call, the error flag, the keys of the result and the messages SHALL be equal to the recorded values. The test SHALL ignore ids, dates, URLs, avatars and the order of keys.

#### Scenario: Recorded call
- **WHEN** the contract test runs the recorded call of the transition tool with the id `999`
- **THEN** the simulator gives an error with the same message as the recorded result
