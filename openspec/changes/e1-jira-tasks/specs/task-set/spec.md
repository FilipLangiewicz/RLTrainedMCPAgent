## MODIFIED Requirements

### Requirement: Task format
A task SHALL be one record with the same `id` in three files. `queries.json` SHALL give the author and the instruction. `solutions.json` SHALL give the reference tool calls and a final answer. `expected.json` SHALL give the board, the category, the difficulty and the expected result: `changes` for a change category, `answer` for `query`, `refusal_kind` for `refusal`. The formats are in `docs/TASKS.md`.

#### Scenario: Read a task
- **WHEN** a program loads a split
- **THEN** each task has an id, an author, an instruction, reference calls, a final answer, a board, a category, a difficulty and an expected result

#### Scenario: Query task
- **WHEN** a program loads a task of the category `query`
- **THEN** the task has an expected answer with a type and a value, and no expected changes

### Requirement: Task files
The task files of a split SHALL be `data/tasks/<split>/queries.json`, `solutions.json` and `expected.json`. The authors SHALL be in `data/tasks/<split>/personas.json`. The boards SHALL be in `data/environments/`, one JSON file for each board. A split without files SHALL load as an empty list.

#### Scenario: Load the test set
- **WHEN** a program loads the split `test`
- **THEN** it reads the three task files of `data/tasks/test/`
- **AND** it gets 200 tasks

#### Scenario: Missing train set
- **WHEN** a program loads the split `train` and the folder has no task files
- **THEN** the result is an empty list and there is no error

### Requirement: Expected changes from the reference solution
A test SHALL apply the reference calls of each task to a new copy of its board with the simulator tools. For a change category, the difference of the board SHALL be equal to the expected changes. For `query` and `refusal`, the board SHALL not change. No reference call SHALL give an error.

#### Scenario: Correct reference solution
- **WHEN** the test applies the reference calls of a task and the verifier grades the result with the reference answer
- **THEN** the grade is `correct` or `correct_refusal`

### Requirement: Mix of difficulties
The test set SHALL have at least 150 tasks. At least 30% of them SHALL be `easy`, at least 40% SHALL be `multi_step`, and at least 10% SHALL be `refusal`. The refusal tasks SHALL include the four refusal kinds.

#### Scenario: Count of the test set
- **WHEN** a test counts the tasks of the test set by difficulty
- **THEN** the counts satisfy the limits of this requirement

### Requirement: Words of a user
An instruction SHALL use the words of a user, not the names of tools, account ids or transition ids. An `easy` task SHALL give each issue key that it changes or reads. Each instruction text SHALL be different.

#### Scenario: Person in the dative case
- **WHEN** a task asks to assign `WEB-7` to Michał Krawczyk
- **THEN** the instruction can say "Dajcie WEB-7 Michałowi"
- **AND** the instruction does not contain the account id

#### Scenario: Key of an easy task
- **WHEN** a test reads an `easy` task that changes the issue `WEB-12`
- **THEN** the instruction contains `WEB-12`

### Requirement: Separate splits
The test tasks and the train tasks SHALL use different boards. No instruction text and no issue summary SHALL occur in both splits.

#### Scenario: Overlap check
- **WHEN** the tests compare the two splits
- **THEN** no board name, no instruction text and no issue summary occur in both splits

### Requirement: Frozen test set
After E1, the content of the task files of `data/tasks/test/` and of the test boards SHALL not change. A test SHALL compare these files with stored checksums. The checksums SHALL ignore the line ends.

#### Scenario: Changed test file
- **WHEN** a person changes one task of the test set after the freeze
- **THEN** the checksum test fails

## ADDED Requirements

### Requirement: Categories
Each task SHALL have one of 8 categories: `query`, `update`, `log`, `create`, `sprint`, `bulk`, `workflow`, `refusal`. The tasks of `bulk` and `workflow` SHALL be `multi_step`. The tasks of `refusal` SHALL be `refusal`, and only they.

#### Scenario: Category and difficulty
- **WHEN** a test reads all tasks
- **THEN** each task of the category `bulk` has the difficulty `multi_step`

### Requirement: Refusal kinds
A refusal task SHALL have one of these kinds: `no_tool`, `missing_entity`, `ambiguous`, `out_of_domain`. The reference answer of a refusal task SHALL start with `ODMOWA:`, and its reference calls SHALL use only read tools.

#### Scenario: Ambiguous person
- **WHEN** the board `test-web` has two persons with the first name Anna and the instruction asks to assign an issue to Ania
- **THEN** the task is a refusal task of the kind `ambiguous`

### Requirement: Agreement of the task files
The loader SHALL stop with an error that names the task id when the three files do not have the same ids, when a task names an unknown board or author, or when a category, a difficulty, an answer type or a refusal kind is not allowed.

#### Scenario: Missing solution
- **WHEN** `queries.json` has the id `test-201` and `solutions.json` does not have it
- **THEN** the loader stops with an error that names `test-201`

## REMOVED Requirements

### Requirement: Deterministic generation
**Reason**: The task files are data that the team writes, reviews and corrects. The code does not generate tasks.
**Migration**: Use the files `queries.json`, `solutions.json` and `expected.json` of each split.
