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

### Research of the real Jira MCP servers

- Add `JIRA_MCP.md`. It describes the two real MCP servers for Jira: the Atlassian Rovo MCP Server (v2, 52 Jira tools) and `mcp-atlassian` 0.23.1 (63 Jira tools).
- It lists all Jira tools of both servers and maps the 7 simulator tools to them.
- The simulator tools are our own design. They cover only a subset of Jira: issues, persons, sprints and comments.
- The check of `mcp-atlassian` used its source code from PyPI. The data of the Rovo server comes from the documentation of Atlassian.
- Add `docs/MODELS.md`. It lists six candidate models from three families: Qwen3.5 (2B, 4B), Bielik v3 (1.5B, 4.5B) and Gemma 4 (E2B, E4B).
- For each model, the file gives the license, the release date, the links to Hugging Face and Kaggle, and an estimate of the VRAM.
- The team removes Qwen3 from the candidates. The decision about SFT and RL for each model is open.

### Decision: mcp-atlassian

- The team selects `mcp-atlassian` 0.23.1 as the reference for real Jira. The simulator must give the same tools as this server.
- The team does not use the results of `baseline-v1`. The new candidate models are in `docs/MODELS.md`.
- Move `JIRA_MCP.md` to `docs/JIRA_MCP.md`. Remove the Rovo MCP Server and the comparison with the old simulator tools.
- Add the pinned version, the sources and an estimate of the schema size of each of the 63 Jira tools.
- Add a proposal: 12 tools, with a maximum of 15. The main limit is the context of 8192 tokens of Bielik-1.5B.

### Contracts of the selected Jira tools

- Select 13 tools of `mcp-atlassian` 0.23.1. They cover search, issue creation, assignment, status, labels, comments, worklogs and sprints.
- Each operation has one way. `docs/JIRA_TOOLS.md` gives the operations, the used arguments and the result formats.
- Add `data/mcp_atlassian_tools.json`: the exact schemas of the 13 tools from `list_tools()` of the real server.
- Measure the size of the schemas: 3820 tokens (Gemma 4 E2B) and 4679 tokens (Qwen3.5-2B). All 63 tools have 12979 and 15708 tokens.
- Add to `docs/JIRA_MCP.md` the procedures for a Jira Cloud site, an API token, the start of the server and a new copy of the schemas.
- Add `jira_get_worklog` to the selected tools. Now 14 tools are selected. The schemas have 3904 tokens (Gemma 4 E2B) and 4806 tokens (Qwen3.5-2B).

### Next steps

1. Make a Jira Cloud site (Free plan) and an API token (see `docs/JIRA_MCP.md`).
2. Run the 14 tools on the site. Record their real results and error messages.
3. Start a new OpenSpec change: the simulator with the contracts of `docs/JIRA_TOOLS.md`.
4. Make the task set again for the new tools, and a contract test with the recorded results.
5. Run a new baseline with the models of `docs/MODELS.md`.

## 2026-11-03

### Kaggle account for each project

- Add `jobs/kaggle.sh`. It runs the Kaggle CLI of `.venv`. If `.kaggle/access_token` of the project is not empty, the CLI uses this token. Otherwise the CLI uses `~/.kaggle/access_token`.
- `jobs/wait.sh` calls `jobs/kaggle.sh`. Thus it uses the same account as the push.
- `KAGGLE.md`: add the selection of the account. All Kaggle commands use `bash jobs/kaggle.sh`. The user in the kernel id must be the selected account.
- `.gitignore`: add `.kaggle/`.

### Test of the MCP server on Jira Cloud

- The Jira Cloud site `combains.atlassian.net` exists. It has one team-managed Scrum project `SCRUM` with board 1 and two sprints.
- The account of the API token is a Jira administrator and an administrator of the project `SCRUM`. It can delete issues.
- Run all 14 selected tools of `mcp-atlassian` 0.23.1 on the site. All tools operate. The schemas of the live server agree with `data/mcp_atlassian_tools.json`.
- Add `data/jira_recorded_results.json`: 42 calls with their real results and errors. The e-mail addresses are replaced with `user@example.com`.
- Add the section "Behavior of real Jira" to `docs/JIRA_TOOLS.md`. Correct the results of `jira_search`, `jira_get_transitions` and `jira_add_comment`.
- Important fact: the results show translated names (`W toku`, `Zadanie`), but JQL accepts only the original names (`In Progress`, `Task`). A translated name in JQL returns an empty list without an error.
- Two tools hide an error: `jira_create_issue` with an unknown assignee, and `jira_add_worklog` with an incorrect time.
- Invite 6 persons with aliases of the e-mail address of the team. Their accounts are not active until a person accepts each invitation and sets the name.
- Delete the test issues `SCRUM-5` to `SCRUM-7`.

### Language of Jira

- The team selects English as the Jira language of the API account. The issues, the comments and the tasks can be in Polish or in English.
- Set the Jira language with `PUT /rest/api/3/mypreferences/locale`. Now the results and JQL use the same names (`In Progress`, `Task`, `Done`).
- Record the results of the 14 tools again. `data/jira_recorded_results.json` now has 43 calls in English.
- The 6 invited persons now have access to Jira. Their display names are still the e-mail aliases.
- Delete the test issues `SCRUM-8` to `SCRUM-12`.

## 2026-11-04

### New test set (not frozen yet)

- The team decides: the data comes before the code. The OpenSpec change of the new simulator does not make the task set. It only reads the task files.
- Add 5 test boards in `data/environments/`: `test-web`, `test-app`, `test-api`, `test-data`, `test-ops`. They are the Jira projects of one invented company: JayWalk, a brand of sport shoes with an online shop.
- Each board has 40 issues, 7 or 8 persons and 4 sprints. Each board has a person who is not active and two persons with the same first name.
- Add the test set in `data/tasks/test/`: `queries.json` (instructions), `solutions.json` (correct tool calls and answers), `expected.json` (expected results) and `personas.json` (authors).
- The test set has 200 tasks in 8 categories: 72 `easy`, 103 `multi_step` and 25 `refusal`.
- Each instruction has one of 16 authors. All instructions of one author have the same style.
- A temporary script outside the repository made the files and checked them: each key exists, each search gives the expected issues, each change category has a change, and the counts agree.
- Add `docs/TASKS.md`: the flow, the categories, the counts, the authors, the file formats and the review procedure.
- Check two facts on the Jira Cloud site: `openSprints()` finds only the active sprint, and `~` finds only whole words. Add them to `docs/JIRA_TOOLS.md`.
- The old files (`data/tasks/*/tasks.jsonl`, the old boards) stay until the new simulator replaces the old one. The old tests pass.

### Not complete

- The team must review the test set. Then the test set is frozen.
- The train set does not exist yet.

### Plan of the OpenSpec change `e1-jira-tasks`

- Rewrite the proposal and the delta specs. The change does not generate tasks. It reads the task files and checks them.
- Add `design.md`: the modules, the low-level MCP server with the exact schemas, the result formats, the errors, the JQL subset, the verifier and the contract test. It has Mermaid diagrams and tables.
- Add `tasks.md`: 8 groups of tasks. The implementation starts in a new chat with `/opsx:apply e1-jira-tasks`.
- `openspec validate e1-jira-tasks --strict` passes.
- Check on the Jira Cloud site how the server finds a person. `assignee` needs the full name or the e-mail. Case and Polish letters do not matter. A first name only gives an error. Add this to `docs/JIRA_TOOLS.md`.
- The team set the display names of the 6 invited accounts: Rudolf Igor, Katarzyna Wisniewska, John Pork, Robert Małysz, Daria Wasilewska and Barbara Liskov.

## 2026-11-05

### Removal of the old data

- Remove the old boards (`data/environments/test-0*.json`, `train-*.json`) and the old task files (`data/tasks/*/tasks.jsonl`).
- Remove `tests/test_tasks.py` and `tests/test_evaluate.py`. They read the old files. The OpenSpec change `e1-jira-tasks` writes new tests for the loader and the evaluation.
- The old code in `src/` stays until the implementation of `e1-jira-tasks`. 81 tests pass.

### Decisions about the models and the baseline

- The team does not use the old baseline `baseline-v1`.
- The candidate models are the six models of `docs/MODELS.md`.
- The weights of all six models go into private Kaggle Models of the project account, one time. This also applies to Gemma 4, because the official Kaggle copy can go away.
- Each model gets its own Kaggle notebook. A failure then affects only one model, and the output stays under the disk limit of Kaggle.
- The jobs record the Hugging Face commit and the Kaggle Model version. Later jobs attach the frozen weights and need no internet.
- The download of the weights and the new baseline are research work. They are not part of an OpenSpec change. `jobs/JOBS.md` records them.
- The thinking mode comes from the config of a run (`model.thinking`), not from `.env`. Thus `metrics.json` records it.

### Next steps

1. Complete the OpenSpec change `e1-jira-tasks` (plan, then implementation in a new chat).
2. After the change: make the Kaggle jobs for the weights of the six models.
3. Then: run the new baseline with the frozen weights.

### Revision of the OpenSpec change `e1-jira-tasks`

- Add the capability `model-layer`: one interface for all models, the families `qwen3.5`, `gemma4` and `bielik`, the backends `transformers`, `openai` and `scripted`, and the thinking switch from the config of a run.
- Bielik has no native tool calls. Its family puts the tool list and the tool-call format into the system prompt.
- Move the system prompts into versioned files in `prompts/` (`system-v2.md`, `tools-bielik-v1.md`). The run records the version and the SHA-256 of the prompt file.
- The download of the weights and the runs of real models are out of scope of the change.
- Add the design decisions D14 (model layer) and D15 (thinking in the config). Add the task groups "Model layer and prompts" and "Agent and evaluation".
- `openspec validate e1-jira-tasks --strict` passes.

### Implementation of the OpenSpec change `e1-jira-tasks`

- `src/environment.py`: the board file in the Jira format, the fixed values of the Jira Cloud site, the operations with the fixed clock, the person rules and `diff()` in the format of `expected.json`.
- `src/jql.py` (new): the JQL subset of design D8 with the semantics of the site.
- `src/tools.py`: a low-level MCP server with the 14 tools of `data/mcp_atlassian_tools.json`. It has the result formats and the error messages of the real server. A failed call does not change the board.
- `src/verifier.py`: the comparison with the expected changes as multisets, the grade of `query` tasks and the answer types. A person name in a Polish case form is correct ("Ewy Mazur").
- `src/tasks.py`: the loader of the three task files and its checks. The old task generator is removed.
- `src/models.py` (new): the model layer with the families `qwen3.5`, `gemma4` and `bielik`, and the backends `transformers`, `openai` and `scripted`. The parsers of Qwen3.5 and Gemma 4 agree with the chat templates of the models.
- `prompts/system-v2.md` and `prompts/tools-bielik-v1.md` (new). The run records the version and the SHA-256 of the prompt.
- `src/agent.py`: only the loop and the trajectory. The default step limit is 25. The thinking text goes into the trajectory.
- `src/evaluate.py`: the new loader, the model layer and the prompt file. `metrics.json` records the model data and the prompt. Each line of `results.jsonl` has the author and the board.
- All 200 reference solutions get `correct` or `correct_refusal` on the simulator. No data file changed.
- The contract test runs the 43 recorded calls. It has three exceptions with reasons: the site issues have no priority, the site project has no type `Bug`, and the site has custom fields.
- The recording showed two rules that are new in `docs/JIRA_TOOLS.md`: the user search accepts one word of the query, and the results show the labels in alphabetical order.
- Decision: in a `missing_entity` refusal task, a read call of the reference solution can give an error (`test-078` reads `APP-140`). The spec of the change has this exception now.
- `docs/MODELS.md` has the keys of the run config.
- Tests: 197 pass, 1 is skipped (the checksum test, until the freeze of the test set).

### Archive of the OpenSpec change `e1-jira-tasks`

- Merge the delta specs into `openspec/specs/`. The new main spec `model-layer` has 6 requirements.
- Move the change to `openspec/changes/archive/`.
- The team did not review or freeze the test set yet. The checksum test stays skipped until the freeze.

## 2026-11-05

### Review of the test set

- The team wrote 31 corrections of instructions as comments on the commit `bb7bd91` (`data/tasks/test/queries.json`).
- Apply 30 corrections to `queries.json`. The corrections make the requests clearer ("Zmień APP-24 na Highest.") or remove the strange remarks of the author Rudolf Igor. The expected result of each task does not change.
- Do not apply the correction of `test-115`. The new text "Stwórz issue - ..." asks for a new issue, but the task changes the existing issue `API-24`. The team kept the old text.
- `solutions.json` and `expected.json` do not change.
- Check: the evaluation with the reference calls gives the score 1.0 on all 200 tasks. The only tool error is the intended read of `APP-140` in `test-078`.
- The test set is not frozen yet.

### Freeze of the test set

- Freeze the test set: `tests/test_tasks.py` has the SHA-256 checksums of `queries.json`, `solutions.json`, `expected.json` and the 5 test boards. The checksums ignore the line ends.
- From now on, a change of these files needs a new run of all variants (see `AGENTS.md`).

## 2026-11-05

### Branch names, health indicators and report

- Branch `06-e1-baselines` starts the work on the weights and the baselines of the six models.
- `AGENTS.md`: name each branch `NN-<topic>`. NN is the next number of a branch. Old branches keep their names.
- `src/evaluate.py`: each result line has the fields `tool_calls`, `empty_answer` and `garbled`. A model output is garbled if it has the character U+FFFD or fewer than 30% letters. NaN logits give a row of `!`.
- `metrics.json` has the new group `health`: empty answers, garbled tasks, tasks without a tool call, tasks with an invalid call and tasks that stop at the step limit.
- `src/evaluate.py` writes `report-<codename>.md` in the output folder: a table with one row for each task (instruction, calls, answer of the model, reason, points).
- 199 tests pass and 2 are skipped.
- Rename the report to `report-<codename>.md`, so the file name shows the model.
- `AGENTS.md`: a job keeps its small output files in its own folder. Only `report-<codename>.md` of a baseline goes to `data/results/baseline/`. `trajectories.jsonl` stays on Kaggle.
- Move `prompts/` to `src/prompts/`. A prompt is a part of the code. Old entries of this worklog keep the old path.

### Smoke test of the six models

- Add the job `smoke-baselines`: four test tasks for each model, prompt `v2`, `float16`. The weights of all six models are in private Kaggle Models (`idm-pro-<model>`, variation `base`).
- Result: all six models make tool calls, the parsers work, and no output is garbled. Gemma 4 E4B runs on two GPUs with `device: auto`.
- Bielik 1.5B and 4.5B run out of GPU memory for a long prompt. Qwen3.5-2B loops and makes up to 83 calls in one task.
- Gemma 4 and Qwen3.5-4B often refuse a possible task ("no issue key"), also when the key is in the instruction.
- Fix `src/agent.py`: tool arguments that are not an object are an invalid call. Before, they stopped the task with a TypeError.

### Freeze of the system prompt

- Add `src/prompts/system-v3.md`. It is the prompt of the baseline and of all later variants. The project measures only the effect of LoRA and RL, so the prompt does not change.
- The prompt is in English. The answer to the user is in Polish. All six models get the same text.
- Bielik has no native tool calls. Its tool list goes into the same system message after the text of the prompt (`src/prompts/tools-bielik-v2.md`). The list is compact, because the full JSON schemas need more than 7000 tokens with the Bielik tokenizer. The context of Bielik does not change.
- `DEFAULT_PROMPT` is `v3`. `tests/test_models.py` has the SHA-256 of `system-v3.md` and `tools-bielik-v2.md`.
- A change of these files needs a new version and a new run of all variants.
- The prompt was not tuned on the test set. A validation set does not exist yet.

### Fast kernels of Qwen3.5

- Qwen3.5 used the slow reference code of PyTorch for its linear attention. The log of Kaggle said that `flash-linear-attention` is not installed.
- Add `flash-linear-attention` to `requirements.in`. The locks get 3 new packages: `einops`, `fla-core` and `flash-linear-attention`. They are pure Python and use the Triton of PyTorch.
- Add `--no-warn-conflicts` to the `pip install` of the jobs. Thus the log has no warnings about the packages of Kaggle that the project does not use.
- The package `causal_conv1d` needs a CUDA build. The project does not install it.

### Result of the smoke test with all six models

- Prompt `v3`, four tasks for each model. No model has a garbled output. All models call the tools.
- `flash-linear-attention` did not make Qwen3.5 faster. Qwen3.5-4B ran out of GPU memory in all four tasks (it had no error before). Remove the package from `requirements.in` and from both locks.
- The check for garbled output marked a stray Gemma token (`<|"|>`) as garbled. Now it checks only outputs of 8 or more characters.
- Small models make the same failed call again and again (`jira_get_issue` with a made-up key, a JQL with `=` on `summary`). This is the behavior that SFT and RL must improve.
- The run with `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` and the two Qwen models checks the removal of the package.

### Correction about flash-linear-attention

- Version 6 of the smoke test ran the two Qwen models without `flash-linear-attention`. Qwen3.5-4B still ran out of GPU memory in 2 of 4 tasks. One request was 8.86 GiB, the same as with the package. Thus the package was not the cause.
- The size of the request fits the logits of the whole prompt in `float32`: about 9600 tokens, a vocabulary of about 248000 and 4 bytes for each value. The check of this cause is open.

### Cause of the out-of-memory errors on the T4

- The real cause is the attention of the full layers, not the logits and not `flash-linear-attention`. On a T4, PyTorch has no flash kernel for grouped-query attention. It uses the math kernel, which builds a full attention matrix in `float32`.
- Measured for Qwen3.5-4B with a prompt of 10000 tokens: a request of 5.96 GiB, which is 16 heads × 10000² × 4 bytes. The measurement is in `jobs/runs/2026-11-05_10_bench-sdpa/`.
- Fix: `avoid_gqa_in_sdpa()` in `src/models.py`. On a GPU older than Ampere, `transformers` repeats the key and value heads, and PyTorch uses the memory-efficient kernel. The peak memory of Qwen3.5-2B at 10000 tokens falls from 12.1 GB to 5.1 GB.
- Run the models that ran out of memory again: Qwen3.5 2B and 4B, and Bielik 4.5B. The other models work, and the baseline run covers them.
- `flash-linear-attention` works on the T4 but does not make the model faster (Triton compiles again for each new length). Do not install it. `causal_conv1d` has no wheel for this version of PyTorch and gives a very small gain.
- Result of the run with the fix: Qwen3.5 2B and 4B and Bielik 4.5B have no memory errors. Qwen3.5-4B makes 2 of 4 tasks correct, among them a task with 38 tool calls. One task of Bielik 4.5B stops at the step limit after 50 failed calls (872 s).

### Rule that ends a loop

- Loops use most of the time of a run. In the smoke test of Bielik 4.5B, one task took 872 s of 958 s.
- Add `agent.loop_limit` (default 3). The same tool call, with the same name and arguments, 3 times in a row ends the task with the stop reason `loop`. The grade comes from the state of the board, as for the step limit.
- The value is in the config of a run and not in `.env`, so `metrics.json` records it. `metrics.json` has the new count `loop_tasks`.
- The rule is part of the protocol. The baseline, SFT and RL use the same value.
- Version 8 of the smoke test runs all six models. The fix of the attention kernel and the loop rule change the code path of all models.
- Result of the smoke test with the rule: all six models run on the final code. The rule ends 3 tasks of Qwen3.5-2B and 1 task of Qwen3.5-4B, but it saves little time. The calls of a loop often differ (Bielik 4.5B: 50 failed calls in one task, 891 s).

### Rule of tool errors in a row

- Add `agent.error_limit` (default 5). Five tool errors in a row end the task with the stop reason `loop`. A call that works resets the count.
- The cause: Bielik 4.5B made 50 different calls and each one failed. The rule of equal calls did not stop it.
- The value is in the config of a run. The baseline, SFT and RL use the same value. A trained model must make fewer errors in a row than the limit.
- Version 9 of the smoke test runs only the two models that this rule changes: Qwen3.5-2B and Bielik 4.5B.
- Result with the rule of 5 errors: Bielik 4.5B needs 159 s for the 4 tasks (before 980 s). The task `test-010` ends after 6 failed calls in 67 s (before 50 calls in 891 s). Qwen3.5-2B needs 335 s (before 496 s). The grades did not change.
- `load_weights` disables the progress bar "Loading weights". The bar wrote hundreds of lines into the log.

### Baseline jobs

- Add six jobs `baseline-<model>` (folders 11 to 16), one for each model. Each job runs the 200 test tasks with the prompt `v3`, `float16`, `max_steps` 25, `loop_limit` 3 and `error_limit` 5. The config has `model.thinking: false`.
- A model that fits on one GPU runs as two processes (one half of the tasks on each GPU). The job merges the halves. Gemma 4 E4B runs as one process on both GPUs.
- Order of the queue, from the shortest job to the longest: Gemma E2B, Gemma E4B, Bielik 1.5B, Bielik 4.5B, Qwen3.5-2B, Qwen3.5-4B. Kaggle allows 2 sessions at the same time.
- The tasks and the boards come from the clone of the branch. They are not in a Kaggle dataset.

### Baseline of Gemma 4 E2B

- Job `baseline-gemma-4-e2b`: score 0.305 on 200 test tasks (correct 0.195, correct refusal 0.110). `easy` 0.458, `multi_step` 0.058, `refusal` 0.880.
- The model calls no tool in 75 of 200 tasks. No output is garbled, one task ends with the stop reason `loop`. The job needs 870 s.
- The report is in `data/results/baseline/report-baseline-gemma-4-e2b.md`.

### Error analysis of Gemma 4 E2B

- Add the job `calls-digest`. This CPU job reads `trajectories.jsonl` on Kaggle and writes a small file with the tool calls. Thus `trajectories.jsonl` stays on Kaggle.
- Add the column `Why` and the section "Error analysis" to `data/results/baseline/report-baseline-gemma-4-e2b.md`. All grades stay as they are.
- The model does not need an issue key: in 44 incorrect tasks, the search of the reference solution finds exactly one issue. Task `test-159` has 3 matches.
- The team treats the project search as a skill that the model does not have. The instruction and the prompt `v3` do not name the project, but the model can find it with a tool. The prompt does not change.
- The reference solutions do not show the step that finds the project. The training examples must have this step.
- In 6 of 22 correct refusals, the reason of the model is wrong. The verifier checks only the prefix `ODMOWA:`.

### Baseline and error analysis of Gemma 4 E4B

- Job `baseline-gemma-4-e4b`: score 0.325 on 200 test tasks (correct 0.25, correct refusal 0.075). `easy` 0.556, `multi_step` 0.097, `refusal` 0.600. 73 tasks have no tool call. The job needs 2992 s.
- In 7 of 10 incorrect refusal tasks, the meaning is a correct refusal, but the answer does not start with `ODMOWA:`.
- The report is in `data/results/baseline/report-baseline-gemma-4-e4b.md`, with the column `Why` and the section "Error analysis".

### Baseline of Bielik 1.5B

- Bielik 1.5B: score 0.050 (all correct, no correct refusal). `easy` 0.139, `multi_step` 0.000, `refusal` 0.000. 53 tasks have an invalid call, 32 tasks end by the loop rules and 7 by the step limit. The job needs 2541 s.
- The report is in `data/results/baseline/report-baseline-bielik-1-5b-v3.md`.

### Error analysis of Bielik 1.5B

- Add the column `Why` and the section "Error analysis" to `data/results/baseline/report-baseline-bielik-1-5b-v3.md`. All grades stay as they are.
- The parser is correct. The broken calls are real output of the model.
- The generation of Bielik does not stop at `</tool_call>`. In 160 of 200 tasks, the model writes more than one call in one output. Gemma 4 E2B does this in 4 tasks and E4B in 6 tasks. The effect on the score is not known.
- The team does not add a stop rule. The training must teach the model to stop after a call.
- The model copies examples from the tool descriptions, for example `PROJ-123`.

### Baselines and error analysis of Bielik 4.5B, Qwen3.5-2B and Qwen3.5-4B

- Bielik 4.5B: score 0.120 (all correct, no correct refusal). `easy` 0.319, `multi_step` 0.010, `refusal` 0.000. The job needs 14252 s.
- Qwen3.5-2B: score 0.120 (correct 0.105, correct refusal 0.015). `easy` 0.264, `multi_step` 0.019, `refusal` 0.120. The job needs 10886 s.
- Qwen3.5-4B: score 0.155 (correct 0.120, correct refusal 0.035). `easy` 0.222, `multi_step` 0.078, `refusal` 0.280. The job needs 9666 s.
- Copy the three reports to `data/results/baseline/`. Add the column `Why` and the section "Error analysis" to each report. All grades stay as they are.
- Version 4 of `calls-digest` gives the tool calls of these three baselines. `trajectories.jsonl` stays on Kaggle.
- The projects `PROJ`, `ACV2`, `DEV` and `DT` that the models use are examples in the tool descriptions.

### Open problem: the score of Qwen3.5-4B is too low

- `test-031` stops with a GPU memory error. After it, the first process cannot get GPU memory. The 84 odd tasks from `test-033` to `test-199` fail with no call.
- `test-148` stops with the same error, and `test-150` of the second process fails with no call. Then the second process continues normally.
- These 85 tasks have 0 points, but the model did not run on them. On the 115 tasks that ran, the score is 0.270 (31 of 115). These tasks are not a random sample.
- The exact cause is not confirmed. The code does not free the GPU memory after this error.
- Bielik 4.5B has this error in 2 tasks, and its next tasks run normally. The other four baselines have no such error.
- The team must decide about a fix and a new run. A new run changes the Why cells of the 85 tasks.
