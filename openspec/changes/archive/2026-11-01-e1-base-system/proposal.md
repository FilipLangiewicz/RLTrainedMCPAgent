# Proposal

## Why

Milestone E1 (2026-11-16) needs a base system that operates end-to-end, a test set with expected results, and a baseline score. The repository has only the structure and no code. The course also asks for more than 100 test examples and a first baseline measurement in the week after lecture 4.

## What Changes

- Add a simulator of a project management system (the environment). It keeps a board with persons, sprints and issues in memory. The board data is synthetic.
- Add an MCP server that gives the operations of the environment to a model as tools.
- Add a task format. A task has an instruction in Polish, an initial board, a reference solution and the expected changes.
- Add a generator that makes the test set and the train set from templates with a fixed seed. The test set has easy tasks, multi-step tasks and out-of-scope tasks (correct answer: refusal).
- Add a verifier. It compares the changes of the board with the expected changes and gives one of three grades: correct, incorrect, correct refusal.
- Add an agent loop. The base model `Qwen/Qwen3-1.7B` gets a prompt and the tools, and it calls the tools until it gives a final answer. The loop can also use a model behind an OpenAI-compatible API.
- Add an evaluation. It runs the agent on a task set and writes the result of each task, the metrics, the trajectories and the config of the run.
- Generate and commit the test set (frozen at E1) and a first train set.

## Capabilities

### New Capabilities

- `environment`: the state of a board, the operations on it, and the changes between two states.
- `environment-tools`: the MCP server and the contract of each tool (arguments, result, errors).
- `task-set`: the task format, the generator of tasks, and the rules for the train set and the test set.
- `task-verifier`: the grade of one task from the initial state, the final state and the final answer of the agent.
- `agent-loop`: the loop of one model with the tools for one task, and the trajectory that it records.
- `evaluation`: the run of the agent on a task set, the result files and the metrics.

### Modified Capabilities

None. The project has no specs yet.

## Out of Scope

- The baseline run on Kaggle. It is research work, so `jobs/JOBS.md` and `docs/WORKLOG.md` record it after this change.
- A run of a reference API model. The agent loop supports such a model, but this change does not run it.
- Fine-tuning (SFT, LoRA) and reinforcement learning (E2, E3).
- The adapter to real Jira (E3).
- Tasks that ask only a question and expect a text answer. In E1, the verifier grades only the board state and refusals.
- A fast inference server (for example vLLM). The baseline uses the transformers library.
- The update of `README.md`. `AGENTS.md` permits it only at the end of a milestone.

## Impact

- New code in `src/` and new tests in `tests/`. The design gives the names of the files.
- New data in `data/environments/` and `data/tasks/`. `data/tasks/test/` stays frozen after E1.
- No new dependencies. The code uses packages from the current lock: `mcp` 2.x, `transformers`, `torch`, `openai`, `pydantic`, `pyyaml`.
