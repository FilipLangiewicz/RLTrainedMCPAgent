# agent-loop Specification

## Purpose

The agent loop lets one language model do one task with the environment tools. It records each step, so that error analysis and later training can use the trajectory.

## Requirements

### Requirement: Loop of one task
The agent SHALL give the model a system prompt, the task instruction and the tool list from the MCP server. While the model calls tools, the agent SHALL run each call on the server and give the result back to the model. The loop SHALL stop when the model gives an answer without a tool call, or when it reaches the step limit.

#### Scenario: Final answer
- **WHEN** the model gives an answer without a tool call
- **THEN** the loop stops and the answer is the final answer

#### Scenario: Step limit
- **WHEN** the model calls tools in each step and the step limit is 15
- **THEN** the loop stops after step 15 with the stop reason `max_steps`

### Requirement: System prompt
The system prompt SHALL come from a file `src/prompts/system-<version>.md`. The config of a run SHALL give the version, and the run SHALL record it. A changed prompt SHALL get a new file and a new version. The prompt `v2` SHALL tell the model to use the tools, to answer in Polish, that the names of statuses, issue types and priorities are in English, that numbers are digits, and to start the answer with `ODMOWA:` when the task is not possible or not clear.

#### Scenario: Recorded prompt
- **WHEN** a run ends
- **THEN** the result of the run contains the version name of the system prompt

#### Scenario: Version of the new prompt
- **WHEN** the config of a run does not give a prompt version
- **THEN** the agent uses `src/prompts/system-v2.md` and records the version `v2`

#### Scenario: Unknown version
- **WHEN** the config gives the prompt version `v9` and the file `src/prompts/system-v9.md` does not exist
- **THEN** the run stops before the first task with an error that names the file

### Requirement: Invalid tool calls
The agent SHALL not stop on an invalid tool call. When the model output has a tool call that the agent cannot parse, or a call of an unknown tool, the agent SHALL give an error message to the model as the tool result and continue. The trajectory SHALL count these errors.

#### Scenario: Broken JSON
- **WHEN** the model output has a tool call with broken JSON
- **THEN** the model gets an error message as the tool result
- **AND** the counter of invalid calls increases by one

### Requirement: Trajectory record
For each task, the agent SHALL record all messages, all tool calls with their arguments and results, the final answer, the stop reason, the number of steps, the number of invalid calls, the input and output tokens, and the time of the task.

#### Scenario: Record after a task
- **WHEN** the agent ends a task
- **THEN** the trajectory has all items of this requirement
