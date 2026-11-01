# Spec Delta

## Purpose

The agent loop lets one language model do one task with the environment tools. It records each step, so that error analysis and later training can use the trajectory.

## ADDED Requirements

### Requirement: Loop of one task
The agent SHALL give the model a system prompt, the task instruction and the tool list from the MCP server. While the model calls tools, the agent SHALL run each call on the server and give the result back to the model. The loop SHALL stop when the model gives an answer without a tool call, or when it reaches the step limit.

#### Scenario: Final answer
- **WHEN** the model gives an answer without a tool call
- **THEN** the loop stops and the answer is the final answer

#### Scenario: Step limit
- **WHEN** the model calls tools in each step and the step limit is 15
- **THEN** the loop stops after step 15 with the stop reason `max_steps`

### Requirement: System prompt
The system prompt SHALL tell the model to use the tools, to answer the user in Polish, and to start the answer with `ODMOWA:` when the tools cannot do the task. The prompt SHALL have a version name that the run records.

#### Scenario: Recorded prompt
- **WHEN** a run ends
- **THEN** the result of the run contains the version name of the system prompt

### Requirement: Invalid tool calls
The agent SHALL not stop on an invalid tool call. When the model output has a tool call that the agent cannot parse, or a call of an unknown tool, the agent SHALL give an error message to the model as the tool result and continue. The trajectory SHALL count these errors.

#### Scenario: Broken JSON
- **WHEN** the model output has a tool call with broken JSON
- **THEN** the model gets an error message as the tool result
- **AND** the counter of invalid calls increases by one

### Requirement: Model backends
The agent SHALL support two backends with the same loop. The `transformers` backend SHALL run a local model, by default `Qwen/Qwen3-1.7B`, with its own chat template and tool-call format. The `openai` backend SHALL use an OpenAI-compatible API with a base URL and a model name from the config. The API key SHALL come only from the environment variables or `.env`.

#### Scenario: Backend from the config
- **WHEN** the config sets the backend `transformers` and the model `Qwen/Qwen3-1.7B`
- **THEN** the agent runs this model locally

### Requirement: Repeatable generation
The agent SHALL use greedy decoding (temperature 0) by default. For Qwen3, the thinking mode SHALL be off by default, and the config SHALL be able to turn it on.

#### Scenario: Two runs
- **WHEN** the agent does the same task two times with the same config on the same machine
- **THEN** the two trajectories are equal

### Requirement: Trajectory record
For each task, the agent SHALL record all messages, all tool calls with their arguments and results, the final answer, the stop reason, the number of steps, the number of invalid calls, the input and output tokens, and the time of the task.

#### Scenario: Record after a task
- **WHEN** the agent ends a task
- **THEN** the trajectory has all items of this requirement
