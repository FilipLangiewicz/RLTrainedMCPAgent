# Worklog

## 2026-11-01

- Create the repository structure.
- Add the project plan (`docs/project.md`) and the course requirements (`docs/task/`).
- Add the Kaggle rules (`KAGGLE.md`) and the job records (`jobs/`).
- Rewrite `AGENTS.md`: the full rules for all agents, the setup of the environment, the link to `KAGGLE.md`.
- Lock the dependencies. `requirements.in` and `requirements-dev.in` have the direct dependencies. `requirements.txt` is the lock for the local machines.
- Add `requirements-kaggle.txt`: the lock for Kaggle, without PyTorch and without the local tools. Thus the PyTorch GPU build of Kaggle stays.
- Add `.gitkeep` to `src/`, `tests/` and `notebooks/`.
- Add a short description to `README.md`.
- Add OpenSpec 1.14.0: the folder `openspec/` and the commands and skills of OpenSpec.
- Add the rules for OpenSpec to `AGENTS.md`. Use it only for changes to the code of the system. Do the plan and the implementation in two chats.
- Add the context and the rules for the artifacts to `openspec/config.yaml`.
- Add the OpenSpec change `e1-base-system` (plan only, no code). It defines the environment, the MCP tools, the task set, the verifier, the agent loop and the evaluation for E1.

### Implementation of `e1-base-system`

- Add six modules in `src/`:
  - `environment.py`: the board models, the board generator, the operations, the search and the difference of two states.
  - `tools.py`: the MCP server with seven tools. `python -m src.tools <board.json>` starts the stdio server.
  - `verifier.py`: the grade of one task (`correct`, `incorrect`, `correct_refusal`) with a reason.
  - `tasks.py`: the task format, the templates and the generator. `python -m src.tasks --seed 2026` makes all files in `data/`.
  - `agent.py`: the system prompt `v1`, the parser of Qwen3 tool calls, the loop and the backends `transformers`, `openai` and `scripted`.
  - `evaluate.py`: the run from a codename, the shards, the merge and `metrics.json`.
- Add one test file for each module in `tests/`. 227 tests pass. 6 tests skip, because some boards have no target for a rare template.
- Add 25 boards in `data/environments/`: `test-01` to `test-05` and `train-01` to `train-20`.
- Add the test set `data/tasks/test/tasks.jsonl`: 200 tasks (70 `easy`, 100 `multi_step`, 30 `refusal`). The test set is frozen. `tests/test_tasks.py` has its SHA-256.
- Add the train set `data/tasks/train/tasks.jsonl`: 1000 tasks (350 `easy`, 500 `multi_step`, 150 `refusal`).
- Each category gets an equal quota of tasks. The test set has 10 tasks for each `easy` and `refusal` category, and 16 or 17 tasks for each `multi_step` category.
- The train category `close_person_sprint` has only 27 tasks, because the train boards have few targets for it. Other `multi_step` categories have more tasks.
- The checksum ignores the line ends, because git on Windows can change them on checkout.
- Smoke test: `Qwen/Qwen3-0.6B`, `float32`, CPU, 2 test tasks. The command ends and writes the three result files. Each task takes approximately 35 s. The model refuses both tasks, so the score is 0. The smoke test checks only the code path.
- uv was not installed on the local machine. Thus the tests ran with `.venv/Scripts/python.exe -m pytest`, with the same packages.
