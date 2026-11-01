# Spec Delta

## Purpose

The environment simulates a project management system. It keeps one board in memory, changes it with operations, and shows the changes between two states of the board.

## ADDED Requirements

### Requirement: Board content
A board SHALL have one project key, a list of persons, a list of sprints and a list of issues. Each person SHALL have an id and a display name. Each sprint SHALL have an id, a name and a state: `closed`, `active` or `future`. Each issue SHALL have a key, a title, a description, a type, a status, a priority, an assignee or none, a set of labels, a sprint or none (backlog), and a list of comments.

#### Scenario: Issue fields
- **WHEN** a client reads an issue of a board
- **THEN** the issue has all the fields of this requirement

### Requirement: Allowed field values
The environment SHALL accept only these values. Type: `bug`, `task`, `story`. Status: `to_do`, `in_progress`, `done`. Priority: `low`, `medium`, `high`, `critical`. An assignee SHALL be the id of a person of the board. A sprint SHALL be the id of a sprint of the board that is not `closed`.

#### Scenario: Value that is not allowed
- **WHEN** an operation sets the status of an issue to `closed`
- **THEN** the operation fails with an error message that lists the allowed values
- **AND** the board does not change

#### Scenario: Unknown person
- **WHEN** an operation sets the assignee to an id that is not on the board
- **THEN** the operation fails with an error message
- **AND** the board does not change

### Requirement: Synthetic data
The data of a board SHALL be synthetic. Person names SHALL come from a fixed list of invented names. The environment SHALL not contain personal data.

#### Scenario: Generated board
- **WHEN** the generator makes a board
- **THEN** each person name comes from the fixed list of invented names

### Requirement: Deterministic generation
The environment SHALL make the same board from the same seed and the same board settings.

#### Scenario: Same seed
- **WHEN** the generator makes two boards with the same seed and settings
- **THEN** the two boards are equal

### Requirement: Save and load
The environment SHALL save a board to a JSON file and load it from this file without a loss of data.

#### Scenario: Round trip
- **WHEN** a board is saved and loaded again
- **THEN** the loaded board is equal to the original board

### Requirement: Search of issues
The environment SHALL find issues with any combination of these filters: status, assignee (a person id or `unassigned`), label, type, priority, sprint (a sprint id or `backlog`), and a text that the title contains. The result SHALL be sorted by the number in the issue key.

#### Scenario: Two filters
- **WHEN** a client searches with the label `frontend` and the type `bug`
- **THEN** the result has all issues of the type `bug` with the label `frontend`, and no other issues

#### Scenario: Unassigned issues
- **WHEN** a client searches with the assignee `unassigned`
- **THEN** the result has only issues without an assignee

### Requirement: Changes of issues
The environment SHALL create an issue, change the fields of an issue, add labels, remove labels and add a comment. A new issue SHALL get the next free number in the project key.

#### Scenario: New issue key
- **WHEN** a client creates an issue on a board with the highest key `WEB-40`
- **THEN** the new issue has the key `WEB-41`

#### Scenario: Unknown issue
- **WHEN** an operation uses the key `WEB-999` and this issue does not exist
- **THEN** the operation fails with an error message
- **AND** the board does not change

### Requirement: Difference of two states
The environment SHALL calculate the difference between two states of one board. The difference SHALL list each changed field of each existing issue with its new value, each new issue with its fields, and each new comment with its text.

#### Scenario: No change
- **WHEN** the environment compares a board with a copy of it
- **THEN** the difference is empty

#### Scenario: Changed assignee
- **WHEN** an operation sets the assignee of `WEB-12` to `u3`
- **THEN** the difference has one entry: the field `assignee` of `WEB-12` with the value `u3`
