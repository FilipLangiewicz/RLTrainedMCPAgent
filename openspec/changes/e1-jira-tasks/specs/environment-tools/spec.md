## MODIFIED Requirements

### Requirement: Tool list
The MCP server SHALL give the 14 tools of `data/mcp_atlassian_tools.json` for one board. Each tool SHALL have the same name, description and argument schema as in this file, without a change. The server SHALL give no other tools.

#### Scenario: List of tools
- **WHEN** an MCP client asks the server for its tools
- **THEN** the client gets 14 tools
- **AND** the name, the description and the argument schema of each tool are equal to the values in `data/mcp_atlassian_tools.json`

### Requirement: Read tools
The read tools SHALL return the keys and the formats of the real server in `data/jira_recorded_results.json`: the search, one issue with its comments, the assignable persons, the agile boards, the sprints of a board, the transitions of an issue and the worklogs of an issue. A read tool SHALL not change the board.

#### Scenario: Search result
- **WHEN** the model searches with a JQL query and a limit of 10
- **THEN** the result has the keys `total`, `start_at`, `max_results` and `issues`
- **AND** `total` is `-1`

#### Scenario: Issue without an assignee
- **WHEN** the model reads an issue without an assignee
- **THEN** the field `assignee` of the result is `{"display_name": "Unassigned"}`

#### Scenario: Transitions
- **WHEN** the model asks for the transitions of an issue
- **THEN** the result is a list of five objects with a number `id` and a `name`

### Requirement: Write tools
The write tools SHALL create an issue, change the fields of an issue (the `fields` argument is a JSON text), do a transition, add a comment, add a worklog, put issues into a sprint and move issues to the backlog. A list of keys SHALL be one text with commas. Each write tool SHALL return the message and the keys of the real server.

#### Scenario: Labels replace the old list
- **WHEN** the model changes the issue `WEB-3` with `{"labels": ["ui"]}` and `WEB-3` had the labels `frontend` and `bug`
- **THEN** `WEB-3` has only the label `ui`

#### Scenario: Assignee by display name
- **WHEN** the model changes an issue with `{"assignee": "Anna Kowalczyk"}` and this person is on the board
- **THEN** the assignee of the issue is the account id of this person

#### Scenario: Two issues to a sprint
- **WHEN** the model puts `"WEB-1,WEB-2"` into the sprint `2`
- **THEN** both issues are in the sprint `2`
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

#### Scenario: Unknown assignee in a change
- **WHEN** the model changes an issue with an assignee that is not on the board
- **THEN** the result is an error that contains "Could not find account ID for user"

## ADDED Requirements

### Requirement: Hidden errors of real Jira
The tools SHALL copy the errors that the real server does not show. The create tool with an unknown assignee SHALL create the issue without an assignee and report success. The worklog tool with a time that it cannot read SHALL log one minute and report success. A person who is not active SHALL not be in the result of the search for assignable persons.

#### Scenario: Unknown assignee in a new issue
- **WHEN** the model creates an issue with the assignee "Nieistniejąca Osoba"
- **THEN** the result is "Issue created successfully"
- **AND** the new issue has no assignee

#### Scenario: Time in words
- **WHEN** the model adds a worklog with the time "półtorej godziny"
- **THEN** the result is "Worklog added successfully"
- **AND** the worklog has 60 seconds

### Requirement: Contract test
A test SHALL run the calls of `data/jira_recorded_results.json` on a board with the same content as the Jira Cloud site at the time of the recording. For each call, the error flag, the keys of the result and the messages SHALL be equal to the recorded values. The test SHALL ignore ids, dates, URLs and avatars.

#### Scenario: Recorded call
- **WHEN** the contract test runs a recorded call of the transition tool with the id `999`
- **THEN** the simulator gives an error with the same message as the recorded result
