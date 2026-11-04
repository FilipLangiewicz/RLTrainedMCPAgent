## Purpose

The model layer gives the agent loop one interface for all language models. It hides the chat format, the tool-call format, the thinking switch and the backend of each model.

## ADDED Requirements

### Requirement: Model interface
Each model SHALL have the same interface: it takes the messages of the conversation and the tool list, and it returns the text of the answer, the tool calls, the parse errors of the tool calls, the thinking text and the numbers of input and output tokens. The agent loop SHALL use only this interface.

#### Scenario: Same loop for two models
- **WHEN** the agent does one task with a model of the family `qwen3.5` and then with a model of the family `gemma4`
- **THEN** the agent loop runs the same code for both models

### Requirement: Model families
The layer SHALL support the families `qwen3.5`, `gemma4` and `bielik`. A family SHALL make the prompt from the messages and the tools with the chat template of the model, and it SHALL find the tool calls in the output text in the format of this family. An unknown family SHALL stop the run before the first task.

#### Scenario: Tool call of a family
- **WHEN** a model of the family `qwen3.5` writes a tool call in its own format
- **THEN** the layer returns one tool call with the name and the arguments
- **AND** the text of the answer does not contain the tool call

#### Scenario: Broken tool call
- **WHEN** the output has a tool call with broken arguments
- **THEN** the layer returns a parse error for this call, and the agent loop gives the error to the model

### Requirement: Tools in the prompt
For a family without native tool calls (`bielik`), the layer SHALL put the tool list and the format of a tool call into the system prompt from the file `prompts/tools-bielik-<version>.md`. The layer SHALL parse the calls of this format.

#### Scenario: Prompt of Bielik
- **WHEN** the agent runs a model of the family `bielik`
- **THEN** the system prompt contains the names of the 14 tools and the format of a tool call

### Requirement: Backends
The layer SHALL support these backends: `transformers` (a model from a local folder or from a Hugging Face id), `openai` (an OpenAI-compatible API with a base URL and a model name from the config) and `scripted` (fixed outputs for the tests). The API key SHALL come only from the environment variables or `.env`. A model from a local folder SHALL load without a connection to the internet.

#### Scenario: Weights from a folder
- **WHEN** the config gives a folder with the weights and the computer has no internet
- **THEN** the `transformers` backend loads the model from the folder

#### Scenario: Scripted model
- **WHEN** a test uses the `scripted` backend with fixed outputs
- **THEN** the agent loop gets these outputs in this order

### Requirement: Thinking switch
The config of a run SHALL give the thinking mode with `model.thinking` (`true` or `false`, default `false`). The family SHALL switch the mode in its own way. When a family has no thinking mode and the config gives `true`, the run SHALL stop before the first task. The thinking text SHALL go into the trajectory, not into the final answer.

#### Scenario: Thinking off
- **WHEN** the config does not give `model.thinking`
- **THEN** the model runs without the thinking mode
- **AND** `metrics.json` records `thinking: false`

#### Scenario: Thinking that the family does not have
- **WHEN** the config gives the family `bielik` and `model.thinking: true`
- **THEN** the run stops with an error that names the family

### Requirement: Repeatable generation
The layer SHALL use greedy decoding (temperature 0) by default. The record of a run SHALL contain the family, the backend, the path or the id of the model, its revision and the thinking mode.

#### Scenario: Two runs
- **WHEN** the agent does the same task two times with the same config on the same machine
- **THEN** the two trajectories are equal
