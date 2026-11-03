## MODIFIED Requirements

### Requirement: Task format
A task SHALL have: a unique id, a split (`train` or `test`), a category, a difficulty (`easy`, `multi_step` or `refusal`), the name of its initial board, an instruction in Polish, a reference solution (a list of tool calls), the expected changes and the expected answer. A task of the category `query` SHALL have an expected answer and no expected changes. A refusal task SHALL have a refusal kind, no expected changes and no expected answer.

#### Scenario: Read a task
- **WHEN** a program loads a task file
- **THEN** each task has all the fields of this requirement

#### Scenario: Query task
- **WHEN** a program loads a task of the category `query`
- **THEN** the task has an expected answer and an empty list of expected changes

### Requirement: Task files
The test set SHALL be in `data/tasks/test/tasks.jsonl`. The train set SHALL be in `data/tasks/train/tasks.jsonl`. The instruction texts of each split SHALL be in `data/tasks/<split>/texts.jsonl`. The initial boards SHALL be in `data/environments/`, one JSON file for each board.

#### Scenario: Load the test set
- **WHEN** a program loads the split `test`
- **THEN** it reads the tasks from `data/tasks/test/tasks.jsonl`

### Requirement: Expected changes from the reference solution
The generator SHALL calculate the expected changes of a task: it applies the reference solution to the initial board with the simulator tools and stores the difference. A task of the categories `update`, `log`, `create`, `sprint`, `bulk` and `workflow` SHALL have at least one expected change. The reference solution SHALL use only the operations of the table "Operations" in `docs/JIRA_TOOLS.md`.

#### Scenario: Correct reference solution
- **WHEN** the reference solution of a task is applied to its initial board
- **THEN** the verifier grades the result as correct

### Requirement: Mix of difficulties
The test set SHALL have at least 150 tasks. At least 30% of them SHALL be `easy`, at least 40% SHALL be `multi_step`, and at least 10% SHALL be `refusal`. The refusal tasks SHALL include the four refusal kinds of the requirement "Refusal kinds".

#### Scenario: Count of the test set
- **WHEN** a test counts the tasks of the test set by difficulty
- **THEN** the counts satisfy the limits of this requirement

### Requirement: Words of a user
An instruction SHALL use the words of a user, not the names of tools, account ids or transition ids. It SHALL name persons by first name or by full name in the correct Polish grammatical case. It SHALL name statuses, sprints and priorities in plain words. An `easy` task SHALL give the issue key. A `multi_step` task SHALL require at least one search or more than one operation. Each instruction text SHALL be different.

#### Scenario: Person in the dative case
- **WHEN** a task asks to assign an issue to the person Anna Kowalczyk
- **THEN** the instruction can say "daj WEB-5 Ani"
- **AND** the instruction does not contain the account id

#### Scenario: Issue without a key
- **WHEN** a `multi_step` task changes one issue
- **THEN** the instruction can describe the issue by its content, for example "ten bug z logowaniem na Safari"

### Requirement: Separate splits
The test tasks and the train tasks SHALL use different initial boards. No instruction text and no issue summary SHALL occur in both splits.

#### Scenario: Overlap check
- **WHEN** the tests compare the two splits
- **THEN** no board name, no instruction text and no issue summary occur in both splits

### Requirement: Deterministic generation
The generator SHALL make the same boards and the same task drafts from the same seed. With the same text files, a command SHALL make the same task files again.

#### Scenario: Generate again
- **WHEN** a user runs the generator two times with the same seed and the same text files
- **THEN** the two outputs are equal byte for byte

## ADDED Requirements

### Requirement: Categories
Each task SHALL have one of 8 categories: `query` (a question about data, no change), `update` (one change of one issue), `log` (a comment or a worklog), `create` (a new issue), `sprint` (a sprint or the backlog), `bulk` (the same change for many issues of a filter), `workflow` (different operations together), `refusal`. The tasks of `bulk` and `workflow` SHALL be `multi_step`. The tasks of `refusal` SHALL be `refusal`.

#### Scenario: Category and difficulty
- **WHEN** a test reads all tasks
- **THEN** each task of the category `bulk` has the difficulty `multi_step`

### Requirement: Counts of categories
The test set SHALL have 200 tasks and the train set SHALL have 1200 tasks, after the review. Each split SHALL have the shares of categories and difficulties of the table in the design. A rejected task SHALL not count.

#### Scenario: Count of a category
- **WHEN** a test counts the test tasks of the category `query`
- **THEN** the count is the value of the table in the design

### Requirement: Refusal kinds
A refusal task SHALL have one of these kinds: `no_tool` (no tool does the operation, for example the deletion of an issue), `missing_entity` (a person, an issue or a sprint that does not exist), `ambiguous` (two or more persons or issues match the words of the user), `out_of_domain` (a request outside the project work).

#### Scenario: Ambiguous person
- **WHEN** a board has two persons with the first name Anna and the instruction asks to assign an issue to Ania
- **THEN** the task is a refusal task of the kind `ambiguous`

### Requirement: Task drafts and texts
The generator SHALL first make task drafts without instruction text. Each draft SHALL list the mentions that the text must contain: an issue key, a person, a label, a sprint or a value. The texts SHALL be in the text file of the split, one line for each task id. The build of the task file SHALL fail for a task without a text or for a text without one of its mentions.

#### Scenario: Missing mention
- **WHEN** the draft of an `easy` task needs the key `WEB-5` and its text does not contain `WEB-5`
- **THEN** the build stops with an error that names the task id

#### Scenario: Person in another case
- **WHEN** the draft needs the person Anna and the text contains "Ani"
- **THEN** the check accepts the mention

### Requirement: Review of the texts
The team SHALL review the texts of both splits before the test set is frozen. A line of the text file SHALL be able to mark a task as rejected. The build SHALL leave out a rejected task.

#### Scenario: Rejected task
- **WHEN** a line of the text file marks the task `test-0042` as rejected
- **THEN** the task file does not contain `test-0042`
