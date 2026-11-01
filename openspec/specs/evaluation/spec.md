# evaluation Specification

## Purpose

The evaluation runs the agent on a task set and gives the numbers that the course grades: the score before and after a change on the same test set, with time and cost.

## Requirements

### Requirement: Run from a config
The evaluation SHALL start from a codename. It SHALL find the config file `<codename>.yaml` in a folder of `jobs/runs/`. The config SHALL give the model settings, the agent settings, the split and an optional limit of tasks.

#### Scenario: Unknown codename
- **WHEN** no config file or more than one config file has the codename
- **THEN** the evaluation stops with an error that lists the found files

### Requirement: Fresh board for each task
The evaluation SHALL load a new copy of the initial board for each task. It SHALL grade each task with the verifier.

#### Scenario: Independent tasks
- **WHEN** the agent changes the board in task 1
- **THEN** task 2 starts from its own unchanged initial board

### Requirement: Result files
The evaluation SHALL write these files into its output folder: `results.jsonl` with one line for each task, `trajectories.jsonl` with the trajectory of each task, and `metrics.json` with the summary. A line of `results.jsonl` SHALL have the task id, the difficulty, the category, the grade, the reason, the steps, the invalid calls, the tokens and the time.

#### Scenario: Files after a run
- **WHEN** a run ends
- **THEN** the output folder has the three files

### Requirement: Metrics
`metrics.json` SHALL have the share of `correct` and `correct_refusal` grades for all tasks, for each difficulty and for each category. It SHALL also have the mean steps, the mean invalid calls, the mean input and output tokens and the mean time of a task, and the total time.

#### Scenario: Score by difficulty
- **WHEN** a run ends on the test set
- **THEN** `metrics.json` has a score for `easy`, for `multi_step` and for `refusal`

### Requirement: Record of the run
`metrics.json` SHALL record the codename, the full config, the model name and its revision, the version of the system prompt, the git commit, the versions of Python, torch and transformers, the device name and the date.

#### Scenario: Reproduce a run
- **WHEN** a person reads `metrics.json` of an old run
- **THEN** the person can find the code, the model and the settings of that run

### Requirement: Shards
The evaluation SHALL run a part of the task set: shard `i` of `n` gets each task whose position modulo `n` is `i`. A separate command SHALL merge the results of all shards into one `metrics.json`.

#### Scenario: Two GPUs
- **WHEN** two processes run shard 0 of 2 and shard 1 of 2
- **THEN** the merged results have each task exactly one time

### Requirement: Error in one task
An exception in one task SHALL not stop the run. The evaluation SHALL grade this task as `incorrect` and record the error message.

#### Scenario: Exception in the model
- **WHEN** the model raises an exception during task 7
- **THEN** task 7 is `incorrect` with the error message
- **AND** the run continues with task 8
