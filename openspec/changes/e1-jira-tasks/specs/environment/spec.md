## MODIFIED Requirements

### Requirement: Board content
A board SHALL have a project (key and name), one agile board (id, name, type `scrum`), a list of persons, a list of sprints and a list of issues. Each person SHALL have an account id, a display name, an e-mail and an active flag. Each sprint SHALL have an id, a name, a state, dates and a goal. Each issue SHALL have the fields in the design: id, key, summary, description, type, status, priority, assignee, reporter, labels, sprint, dates, comments and worklogs.

#### Scenario: Issue fields
- **WHEN** a client reads an issue of a board
- **THEN** the issue has all the fields of this requirement

#### Scenario: Board of the project
- **WHEN** a client reads the agile board of a project
- **THEN** the board has an id, a name and the type `scrum`

### Requirement: Allowed field values
The environment SHALL accept only the values of the Jira Cloud site with the English language. Type: `Task`, `Bug`, `Story`. Status: `Backlog`, `In Progress`, `In review`, `Done`, `Cancelled`. Priority: `Highest`, `High`, `Medium`, `Low`, `Lowest`. Sprint state: `closed`, `active`, `future`. An assignee SHALL be an active person of the board. A sprint of an issue SHALL be a sprint of the board that is not `closed`.

#### Scenario: Value that is not allowed
- **WHEN** an operation sets the priority of an issue to `Wysoki`
- **THEN** the operation fails with the error message of real Jira
- **AND** the board does not change

#### Scenario: Translated issue type
- **WHEN** an operation creates an issue with the type `Zadanie`
- **THEN** the operation fails with the message "Specify a valid issue type"

### Requirement: Synthetic data
The data of a board SHALL be synthetic. Person names SHALL come from a fixed list of invented names, and e-mails SHALL use the domain `example.com`. The names of the persons of the real Jira site SHALL not occur on a board. The environment SHALL not contain personal data.

#### Scenario: Generated board
- **WHEN** the generator makes a board
- **THEN** each person name comes from the fixed list of invented names
- **AND** each e-mail ends with `@example.com`

### Requirement: Search of issues
The environment SHALL find issues with a JQL query in the subset of the design: the fields project, key, status, statusCategory, type, priority, assignee, reporter, labels, sprint, summary and text, the operators `=`, `!=`, `IN`, `NOT IN`, `~`, `IS EMPTY`, `IS NOT EMPTY`, the words `AND`, `OR`, `NOT`, parentheses, the sprint functions and `ORDER BY`. Without `ORDER BY`, the result SHALL be sorted by the number in the key, highest first.

#### Scenario: Two conditions
- **WHEN** a client searches with `project = WEB AND labels = frontend AND type = Bug`
- **THEN** the result has all issues of the type `Bug` with the label `frontend`, and no other issues

#### Scenario: Unassigned issues
- **WHEN** a client searches with `project = WEB AND assignee IS EMPTY`
- **THEN** the result has only issues without an assignee

#### Scenario: Open sprints
- **WHEN** a client searches with `project = WEB AND sprint in openSprints()`
- **THEN** the result has only issues in the active sprint

#### Scenario: Name that does not exist
- **WHEN** a client searches with `project = WEB AND status = "W toku"`
- **THEN** the result is empty and there is no error

### Requirement: Changes of issues
The environment SHALL create an issue, change the fields of an issue, do a status transition, add a comment, add a worklog, put issues into a sprint and move issues to the backlog. A new issue SHALL get the next free number in the project key. A new issue without a priority SHALL get `Medium`, and its status SHALL be `Backlog`.

#### Scenario: New issue key
- **WHEN** a client creates an issue on a board with the highest key `WEB-40`
- **THEN** the new issue has the key `WEB-41`

#### Scenario: Unknown issue
- **WHEN** an operation uses the key `WEB-999` and this issue does not exist
- **THEN** the operation fails with an error message
- **AND** the board does not change

### Requirement: Difference of two states
The environment SHALL calculate the difference between two states of one board. The difference SHALL list each changed field of each existing issue with its new value, each new issue with its fields, each new comment with its text and each new worklog with its time and comment. It SHALL ignore the dates and the ids that an operation sets.

#### Scenario: No change
- **WHEN** the environment compares a board with a copy of it
- **THEN** the difference is empty

#### Scenario: Changed assignee
- **WHEN** an operation sets the assignee of `WEB-12` to the person with the account id `acc-3`
- **THEN** the difference has one entry: the field `assignee` of `WEB-12` with the value `acc-3`

#### Scenario: New worklog
- **WHEN** an operation adds a worklog of `1h 30m` to `WEB-5`
- **THEN** the difference has one entry for `WEB-5` with 5400 seconds and the comment of the worklog

## ADDED Requirements

### Requirement: Status transitions
Each issue SHALL have the transitions of the Jira Cloud site: `Backlog` (11), `In Progress` (21), `In review` (31), `Cancelled` (41) and `Done` (51). Each transition SHALL be available from each status. A transition SHALL set the status of the issue to the status with the same name.

#### Scenario: Transition by id
- **WHEN** an operation does the transition `51` on an issue in the status `In Progress`
- **THEN** the status of the issue is `Done`

#### Scenario: Unknown transition
- **WHEN** an operation does the transition `999`
- **THEN** the operation fails with the message "Transition id '999' is not valid for this issue."

### Requirement: Content file
The generator SHALL take the summaries, the descriptions and the comments of issues from a content file. Each text SHALL have a language (`pl` or `en`) and a split (`train` or `test`). A board of one split SHALL use only the texts of this split.

#### Scenario: Separate texts
- **WHEN** the generator makes a test board
- **THEN** no summary of the board occurs on a train board

### Requirement: Fixed clock
The environment SHALL use a fixed clock for each board. The dates of new comments, worklogs and issues SHALL come from this clock. Thus two runs of the same calls give the same board.

#### Scenario: Same calls two times
- **WHEN** a client applies the same calls to two copies of one board
- **THEN** the two final boards are equal
