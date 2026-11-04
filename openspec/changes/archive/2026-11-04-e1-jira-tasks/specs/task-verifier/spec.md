## MODIFIED Requirements

### Requirement: Grade of a normal task
For a task of the categories `update`, `log`, `create`, `sprint`, `bulk` and `workflow`, the verifier SHALL give `correct` only when the difference of the board is equal to the expected changes. A missing change or an additional change SHALL give `incorrect`.

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
- **WHEN** the agent creates the expected issue with the assignee "Ewa" and the tool creates it without an assignee
- **THEN** the grade is `incorrect`
- **AND** the reason names the assignee of the new issue

### Requirement: Comparison of values
The verifier SHALL compare labels as sets. It SHALL compare summaries, descriptions, comment texts and worklog comments after normalization: lower case, one space between words, no quotation marks, no Markdown marks and no full stop at the end. It SHALL compare a worklog by its time in seconds, and by its comment only when the expected comment is not `null`. It SHALL match a new issue by its fields, not by its key.

#### Scenario: Comment with other case
- **WHEN** the expected comment is "Czekamy na review" and the actual comment is "czekamy na review."
- **THEN** the comment matches

#### Scenario: Worklog in another format
- **WHEN** the expected worklog is 5400 seconds and the agent logs "90m"
- **THEN** the worklog matches

#### Scenario: Worklog without an expected comment
- **WHEN** the expected worklog comment is `null` and the agent adds a worklog with a comment
- **THEN** the worklog matches

## ADDED Requirements

### Requirement: Grade of a query task
For a task of the category `query`, the verifier SHALL give `correct` only when the board did not change and the final answer contains the expected answer. A refusal answer SHALL give `incorrect`.

#### Scenario: Correct number
- **WHEN** the expected answer is the number 3 and the final answer is "W backlogu są 3 takie bugi."
- **THEN** the grade is `correct`

#### Scenario: Change in a query task
- **WHEN** the agent answers correctly but also adds a comment
- **THEN** the grade is `incorrect`

### Requirement: Comparison of answers
The verifier SHALL check the answer by its type. `keys`: the issue keys in the answer are equal to the expected set. `number`: the answer contains the number as digits. `person`: the answer contains the display name, or the first name in any case when no other person of the board has it. `time`: one time in the answer (for example "7h 30m", "7,5 h", "450 minut") is equal in seconds. `value`: the answer contains the value, without regard to case.

#### Scenario: Additional key
- **WHEN** the expected keys are `WEB-5` and `WEB-6` and the answer names `WEB-5`, `WEB-6` and `WEB-35`
- **THEN** the grade is `incorrect`
- **AND** the reason names `WEB-35`

#### Scenario: Time in hours
- **WHEN** the expected time is 27000 seconds and the answer is "Razem 7,5 h"
- **THEN** the grade is `correct`

#### Scenario: Person with a shared first name
- **WHEN** the expected person is Anna Sikora, the board also has Anna Wróbel, and the answer is "Zajmuje się tym Anna"
- **THEN** the grade is `incorrect`
