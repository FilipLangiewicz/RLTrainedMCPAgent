# Spec Delta

## Purpose

The task set defines the tasks that the agent must do, and the rules that keep the test set fixed and separate from the training data.

## ADDED Requirements

### Requirement: Task format
A task SHALL have: a unique id, a split (`train` or `test`), a category, a difficulty (`easy`, `multi_step` or `refusal`), the name of its initial board, an instruction in Polish, a reference solution (a list of tool calls), and the expected changes. A refusal task SHALL have an empty reference solution and no expected changes.

#### Scenario: Read a task
- **WHEN** a program loads a task file
- **THEN** each task has all the fields of this requirement

### Requirement: Task files
The test set SHALL be in `data/tasks/test/tasks.jsonl`. The train set SHALL be in `data/tasks/train/tasks.jsonl`. The initial boards SHALL be in `data/environments/`, one JSON file for each board.

#### Scenario: Load the test set
- **WHEN** a program loads the split `test`
- **THEN** it reads the tasks from `data/tasks/test/tasks.jsonl`

### Requirement: Expected changes from the reference solution
The generator SHALL calculate the expected changes of a task: it applies the reference solution to the initial board and stores the difference. A task that is not a refusal SHALL have at least one expected change.

#### Scenario: Correct reference solution
- **WHEN** the reference solution of a task is applied to its initial board
- **THEN** the verifier grades the result as correct

### Requirement: Mix of difficulties
The test set SHALL have at least 150 tasks. At least 30% of them SHALL be `easy`, at least 40% SHALL be `multi_step`, and at least 10% SHALL be `refusal`. The refusal tasks SHALL include requests outside the domain, requests for an operation that no tool supports, and requests about a person or an issue that does not exist.

#### Scenario: Count of the test set
- **WHEN** a test counts the tasks of the test set by difficulty
- **THEN** the counts satisfy the limits of this requirement

### Requirement: Words of a user
An instruction SHALL use the words of a user, not the names of tools or field values. It SHALL name persons by first name in the correct Polish grammatical case, and it SHALL name sprints and statuses in plain Polish words. Each category SHALL have more than one instruction text.

#### Scenario: Person in the dative case
- **WHEN** a template asks to assign an issue to the person Anna
- **THEN** the instruction can say "przypisz WEB-5 Ani"
- **AND** the instruction does not contain the person id

### Requirement: Separate splits
The test tasks and the train tasks SHALL use different initial boards. No instruction text SHALL occur in both splits.

#### Scenario: Overlap check
- **WHEN** the tests compare the two splits
- **THEN** no board name and no instruction text occur in both splits

### Requirement: Deterministic generation
The generator SHALL make the same task files from the same seed. A command SHALL make all boards and both task files again.

#### Scenario: Generate again
- **WHEN** a user runs the generator two times with the same seed
- **THEN** the two outputs are equal byte for byte

### Requirement: Frozen test set
After E1, the content of `data/tasks/test/` and of the test boards SHALL not change. A test SHALL compare the test set with a stored checksum.

#### Scenario: Changed test file
- **WHEN** a person changes one task of the test set
- **THEN** the checksum test fails
