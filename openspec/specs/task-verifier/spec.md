# task-verifier Specification

## Purpose

The task verifier grades one task automatically. It gives the grade of the course (correct, incorrect, correct refusal), and later it gives the reward for reinforcement learning.

## Requirements

### Requirement: Grade values
The verifier SHALL give one of three grades for a task: `correct`, `incorrect` or `correct_refusal`. It SHALL also give a short reason for the grade.

#### Scenario: Grade of a run
- **WHEN** the verifier grades a task
- **THEN** the result has one of the three grades and a reason

### Requirement: Grade of a normal task
For a task that is not a refusal, the verifier SHALL give `correct` only when the actual changes of the board are equal to the expected changes. A missing change or an additional change SHALL give `incorrect`.

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

### Requirement: Grade of a refusal task
For a refusal task, the verifier SHALL give `correct_refusal` only when the board did not change and the final answer starts with the refusal marker `ODMOWA:`. The verifier SHALL ignore case and white space at the start of the answer.

#### Scenario: Correct refusal
- **WHEN** the board did not change and the final answer is "ODMOWA: nie mam narzędzia do usunięcia projektu"
- **THEN** the grade is `correct_refusal`

#### Scenario: Change instead of a refusal
- **WHEN** the agent changes the board in a refusal task
- **THEN** the grade is `incorrect`

### Requirement: Comparison of values
The verifier SHALL compare labels as sets. It SHALL compare titles and comment texts after normalization: lower case, one space between words, no quotation marks and no full stop at the end. It SHALL match a new issue by its fields, not by its key.

#### Scenario: Comment with other case
- **WHEN** the expected comment is "Czekamy na review" and the actual comment is "czekamy na review."
- **THEN** the comment matches

### Requirement: Independence from the agent
The verifier SHALL use only the initial board, the final board, the final answer and the task. It SHALL not use the trajectory of the agent.

#### Scenario: Other order of calls
- **WHEN** the agent makes the expected changes in another order than the reference solution
- **THEN** the grade is `correct`
