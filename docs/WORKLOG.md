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

### Archive of `e1-base-system`

- Archive the OpenSpec change `e1-base-system`. The change is now in `openspec/changes/archive/2026-11-01-e1-base-system/`.
- Add six main specs in `openspec/specs/`: `agent-loop`, `environment`, `environment-tools`, `evaluation`, `task-set` and `task-verifier`. They have the requirements of the delta specs of the change.
- `openspec validate --specs --strict` passes for all six specs.
- 227 tests pass and 6 tests skip (`.venv/Scripts/python.exe -m pytest`).

### Baseline job

- Add the job `2026-11-01_01_baseline-v1` and its row in `jobs/JOBS.md`. It runs `Qwen/Qwen3-1.7B` with the prompt `v1` on the 200 test tasks on Kaggle (2x T4).
- Each GPU runs one half of the tasks. Then the job merges the two halves into one `metrics.json`.
- If one half fails, the job does not stop with an error. Thus Kaggle keeps the results of the other half.
- Add `six` to `requirements-dev.in`. `kaggle` 2.2.5 imports `six`, but it does not declare it. Without it, the Kaggle CLI does not start. The lock for Kaggle does not change.

## 2026-11-02

### Results of `baseline-v1`

- Download the results of the job `2026-11-01_01_baseline-v1` into its `output/` folder. The job is complete (commit `ef60350`, torch 2.11.0+cu128, 2x T4, 399 s).
- Score: 0.205 on 200 test tasks. `correct` is 0.055 and `correct_refusal` is 0.150.
- `easy`: 0.157 (11 of 70). `multi_step`: 0.000 (0 of 100). `refusal`: 1.000 (30 of 30).
- The model refuses 151 of 170 possible tasks (`easy` and `multi_step`) at the first step, without a tool call. It writes that it has no access to the board.
- Thus the score of the `refusal` tasks shows only this behavior, not a correct decision.
- The model uses tools in only 20 tasks. It never calls `list_users`.
- In 5 tasks the model gives a first name as the assignee (for example "Michał"). The tool returns an error, and the model refuses.
- In 1 task the model repeats the same `search_issues` call 15 times, until the step limit.
- The correct tasks are in `create_issue` (6), `add_comment` (4) and `change_priority` (1).
- Mean time: 3.5 s for each task. Mean tokens: 1861 input and 59 output.

### Rules for branches and Kaggle

- Change `AGENTS.md`: `run.py` clones the branch of the task, not `main`. A Kaggle job does not need a merge into `main`.
- Change `AGENTS.md`: each branch goes into `main` through a pull request with "Squash and merge". Do not merge a branch into `main` directly.

### Remove `.claude/` from git

- Add `.claude/` to `.gitignore` and remove the commands and skills of OpenSpec from git. The local files stay.
- Change `AGENTS.md`: each team member makes the commands and skills with `openspec init --tools claude`. This command does not change `openspec/`.
