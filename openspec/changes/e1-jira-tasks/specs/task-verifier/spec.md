## MODIFIED Requirements

### Requirement: Grade of a normal task
For a task of the categories `update`, `log`, `create`, `sprint`, `bulk` and `workflow`, the verifier SHALL give `correct` only when the actual changes of the board are equal to the expected changes. A missing change or an additional change SHALL give `incorrect`.

#### Scenario: All expected changes
- **WHEN** the agent makes exactly the expected changes
- **THEN** the grade is `correct`

#### Scenario: Additional change
- **WHEN** the agent makes the expected changes and also changes the priority of another issue
- **THEN** the grade is `incorrect`
- **AND** the reason names the additional change

#### Scenario: Missing change
- **WHEN** the agent assigns two of three expected issues
- **THEN** the grade is `incorrect`
- **AND** the reason names the missing change

#### Scenario: Hidden error of the create tool
- **WHEN** the agent creates the expected issue with an unknown assignee and the tool creates it without an assignee
- **THEN** the grade is `incorrect`
- **AND** the reason names the missing assignee

### Requirement: Comparison of values
The verifier SHALL compare labels as sets. It SHALL compare summaries, comment texts and worklog comments after normalization: lower case, one space between words, no quotation marks, no Markdown marks and no full stop at the end. It SHALL compare a worklog by its time in seconds and its normalized comment. It SHALL match a new issue by its fields, not by its key.

#### Scenario: Comment with other case
- **WHEN** the expected comment is "Czekamy na review" and the actual comment is "czekamy na review."
- **THEN** the comment matches

#### Scenario: Worklog in another format
- **WHEN** the expected worklog is 5400 seconds and the agent logs "90m"
- **THEN** the worklog matches

## ADDED Requirements

### Requirement: Grade of a query task
For a task of the category `query`, the verifier SHALL give `correct` only when the board did not change and the final answer contains the expected answer. The expected answer SHALL have one type: a set of issue keys, a number, a person or a time. A refusal answer SHALL give `incorrect`.

#### Scenario: Correct number
- **WHEN** the expected answer is the number 4 and the final answer is "Anna ma 4 otwarte bugi."
- **THEN** the grade is `correct`

#### Scenario: Change in a query task
- **WHEN** the agent answers correctly but also adds a comment
- **THEN** the grade is `incorrect`

### Requirement: Comparison of answers
For a set of keys, the issue keys in the answer SHALL be equal to the expected set: a missing key or an additional key gives `incorrect`. For a number, the answer SHALL contain this number as digits. For a person, the answer SHALL contain the display name, or the first name when no other person of the board has it. For a time, the verifier SHALL read the times in the answer (for example "3h 30m", "3,5 h", "210 minut") and one of them SHALL be equal in seconds.

#### Scenario: Additional key
- **WHEN** the expected keys are `WEB-3` and `WEB-7` and the answer names `WEB-3`, `WEB-7` and `WEB-9`
- **THEN** the grade is `incorrect`
- **AND** the reason names `WEB-9`

#### Scenario: Time in hours
- **WHEN** the expected time is 12600 seconds and the answer is "Razem 3,5 h"
- **THEN** the grade is `correct`
