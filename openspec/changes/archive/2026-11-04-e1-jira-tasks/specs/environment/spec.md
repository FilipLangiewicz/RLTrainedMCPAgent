## MODIFIED Requirements

### Requirement: Board content
A board SHALL have a project (key and name), one agile board (id, name, type `scrum`), a list of persons, a list of sprints and a list of issues, in the format of `docs/TASKS.md`. Each person SHALL have an account id, a display name, an e-mail and an active flag. Each sprint SHALL have an id, a name, a state, dates and a goal. Each issue SHALL have an id, a key, a summary, a description, a type, a status, a priority, an assignee, a reporter, labels, a sprint, dates, comments and worklogs.

#### Scenario: Issue fields
- **WHEN** a client reads an issue of a board
- **THEN** the issue has all the fields of this requirement

#### Scenario: Test boards
- **WHEN** the environment loads each file `data/environments/test-*.json` with a letter after `test-`
- **THEN** each file loads without an error

### Requirement: Allowed field values
The environment SHALL accept only the values of the Jira Cloud site with the English language. Type: `Task`, `Bug`, `Story`. Status: `Backlog`, `In Progress`, `In review`, `Done`, `Cancelled`. Priority: `Highest`, `High`, `Medium`, `Low`, `Lowest`. Sprint state: `closed`, `active`, `future`. An assignee SHALL be an active person of the board. A sprint of an issue SHALL be a sprint of the board that is not `closed`.

#### Scenario: Value that is not allowed
- **WHEN** an operation sets the priority of an issue to `Wysoki`
- **THEN** the operation fails with the error message of real Jira
- **AND** the board does not change

#### Scenario: Unknown person
- **WHEN** an operation sets the assignee to a name that matches no active person of the board
- **THEN** the operation fails with a message that contains "Could not find account ID for user"
- **AND** the board does not change

#### Scenario: Translated issue type
- **WHEN** an operation creates an issue with the type `Zadanie`
- **THEN** the operation fails with the message "Specify a valid issue type"

### Requirement: Synthetic data
The data of a board SHALL be synthetic. Person names SHALL be invented, and e-mails SHALL use the domain `example.com`. The environment SHALL not contain personal data.

#### Scenario: Generated board
- **WHEN** a test reads all persons of all new boards
- **THEN** each e-mail ends with `@example.com`

### Requirement: Search of issues
The environment SHALL find issues with a JQL query in the subset of the design. Without `ORDER BY`, the result SHALL start with the highest number in the key. A query without a condition SHALL fail. A name that does not exist SHALL give an empty result, not an error.

#### Scenario: Two filters
- **WHEN** a client searches with `project = WEB AND labels = frontend AND type = Bug`
- **THEN** the result has all issues of the type `Bug` with the label `frontend`, and no other issues

#### Scenario: Unassigned issues
- **WHEN** a client searches with `project = WEB AND assignee IS EMPTY`
- **THEN** the result has only issues without an assignee

#### Scenario: Open sprints
- **WHEN** a client searches with `project = WEB AND sprint in openSprints()`
- **THEN** the result has only issues in the active sprint, and no issues in future sprints

#### Scenario: Whole words
- **WHEN** a client searches with `project = WEB AND summary ~ "dostawy"`
- **THEN** the result has the issues with the word "dostawy" in the summary
- **AND** it does not have an issue with only the word "dostawa"

#### Scenario: Name that does not exist
- **WHEN** a client searches with `project = WEB AND status = "W toku"`
- **THEN** the result is empty and there is no error

### Requirement: Changes of issues
The environment SHALL create an issue, change the fields of an issue, do a status transition, add a comment, add a worklog, put issues into a sprint and move issues to the backlog. A new issue SHALL get the next free number in the project key, the status `Backlog` and, without a priority, the priority `Medium`.

#### Scenario: New issue key
- **WHEN** a client creates an issue on a board with the highest key `WEB-40`
- **THEN** the new issue has the key `WEB-41`

#### Scenario: Unknown issue
- **WHEN** an operation uses the key `WEB-999` and this issue does not exist
- **THEN** the operation fails with an error message
- **AND** the board does not change

### Requirement: Difference of two states
The environment SHALL calculate the difference between two states of one board in the format of the changes in `expected.json`: changed fields with persons and sprints by name, new comments, new worklogs in seconds, and new issues with their fields. It SHALL ignore the dates and the ids that an operation sets.

#### Scenario: No change
- **WHEN** the environment compares a board with a copy of it
- **THEN** the difference is empty

#### Scenario: Changed assignee
- **WHEN** an operation sets the assignee of `WEB-7` to Ewa Mazur
- **THEN** the difference has one entry: `{"issue": "WEB-7", "field": "assignee", "value": "Ewa Mazur"}`

#### Scenario: New worklog
- **WHEN** an operation adds a worklog of `1h 30m` without a comment to `WEB-5`
- **THEN** the difference has one entry for `WEB-5` with 5400 seconds

## ADDED Requirements

### Requirement: Status transitions
Each issue SHALL have the transitions of the Jira Cloud site: `Backlog` (11), `In Progress` (21), `In review` (31), `Cancelled` (41) and `Done` (51). Each transition SHALL be available from each status. A transition SHALL set the status with the same name. The status category of `Backlog` SHALL be `To Do`, of `Done` SHALL be `Done`, and of the other statuses SHALL be `In Progress`.

#### Scenario: Transition by id
- **WHEN** an operation does the transition `51` on an issue in the status `In Progress`
- **THEN** the status of the issue is `Done`

#### Scenario: Category of a cancelled issue
- **WHEN** a client searches with `statusCategory != Done`
- **THEN** the result also has the issues in the status `Cancelled`

### Requirement: Fixed clock
The environment SHALL use the time `now` of the board file for new comments, worklogs and issues. Thus two runs of the same calls give the same board.

#### Scenario: Same calls two times
- **WHEN** a client applies the same calls to two copies of one board
- **THEN** the two final boards are equal

## REMOVED Requirements

### Requirement: Deterministic generation
**Reason**: The boards are data files that a person reviews and corrects. The code does not generate boards.
**Migration**: Use the files in `data/environments/`.
