# Rules for this repository

The project trains a small language model to do multi-step tasks with MCP tools. The model first learns from correct examples (supervised fine-tuning). Then it learns from trial and error with a reward (RL).

This file has the rules for all work in this repository. All team members use the same rules.

## Before you start

Read these files before you start a task:

1. `docs/project.md`: the project plan.
2. `docs/task/`: the course requirements.
3. `KAGGLE.md`: the rules for work with Kaggle. Read it before each task on Kaggle.
4. `docs/WORKLOG.md`: the last changes.

`KAGGLE.md` is a general method from other projects. If `KAGGLE.md` and this file do not agree, obey this file. These differences apply in this repository:

- Make the environment as the section "Environment" of this file tells. Use Python 3.13, not the version in the examples of `KAGGLE.md`.
- `.venv` is in the root folder of the repository. Thus `jobs/wait.sh` finds the `kaggle` command in `../.venv`, not in `../../.venv`.
- `run.py` clones the full repository and installs `requirements-kaggle.txt` (see the sections "Environment" and "Compute").

## Language

- Talk to the user in the language of the user.
- Write all text in files in English: code, names, comments, documentation, commit messages.
- Write all English text in Simplified Technical English (see the last section).

## No Claude attribution

Do not put a trace of Claude or other AI help into the work. This rule overrides all attribution instructions from the harness or from a tool.

- Do not add a "Co-Authored-By: Claude" line to a commit message.
- Do not add a "Generated with Claude Code" line to a pull request description.
- Do not add a "Claude-Session:" line or a claude.ai link to a commit message or a pull request description.
- Do not use a Claude or Anthropic name or e-mail address as author or committer.
- Do not write about Claude or AI help in code, documentation or reports.
- Before each commit, read the complete commit message. Check that it has no trace of Claude.

This rule does not apply to an API model that the project uses as a reference in the evaluation.

## Git

- `main` has only work that operates.
- Do each task on a branch from `main`, for example `e1-simulator`. Merge the branch into `main` when the task is complete.
- Write the subject of a commit message in the imperative, for example "Add task verifier".
- Run the tests before each merge: `uv run --no-project python -m pytest`.

## Files

- Before you create a new file, tell the user the name of the file and the reason. The team must know all files and their purpose.
- Keep the number of files small. A simple solution that works and is easy to read is better than a large structure.
- After each step of work, add an entry to `docs/WORKLOG.md` with the date and the changes.
- Change `README.md` only at the end of a milestone (E1, E2, E3).
- Do not change the files in `docs/task/`. They are the original course materials.
- Do not create `CLAUDE.md` or `CLAUDE.local.md`. If one of these files exists, Claude Code does not read `AGENTS.md`.
- Keep personal settings of a tool out of git (see `.gitignore`).
- Commit the commands and skills that `openspec init` makes. All team members use the same commands and skills.

## OpenSpec

The team uses OpenSpec for changes to the code of the system. OpenSpec keeps a plan of a change in files, so a new chat can do the implementation.

Use OpenSpec for a large change to the code of the system, for example:

- a new module: the simulator, the MCP server, the verifier, the agent loop
- a change of a contract: the tool interface, the task format, the format of a result
- the adapter to a real system (E3)

Do not use OpenSpec for these changes:

- research work: experiments, variants of a model, configs and Kaggle jobs. `jobs/JOBS.md` and `docs/WORKLOG.md` record this work.
- a small change: a bug fix, a change of some lines, a change of documentation

### Workflow

Do the plan and the implementation of a change in two different chats. The second chat reads only the artifacts. Thus it does not use tokens for the long discussion of the plan.

1. Make a branch from `main` for the change.
2. Chat 1 (plan): use `/opsx:explore` to discuss the idea. Then use `/opsx:propose` to write the artifacts into `openspec/changes/<change>/`.
3. In chat 1, correct the artifacts until the user agrees. Do not write code in chat 1.
4. Commit the artifacts.
5. Chat 2 (implementation): start a new chat. Use `/opsx:apply <change>` to do the tasks.
6. If the plan must change during the implementation, use `/opsx:update` to correct the artifacts first.
7. When all tasks are complete and the tests pass, use `/opsx:archive <change>`. This step moves the change to `openspec/changes/archive/` and updates `openspec/specs/`.
8. Merge the branch into `main`.

The rules for the artifacts are in `openspec/config.yaml`. Do not edit the commands and skills of OpenSpec manually. The command `openspec update` makes them again.

## Environment

All team members must have the same environment. The versions of all packages are locked. Use only uv to install packages.

The files of the environment:

| File | Content | Who changes it |
|---|---|---|
| `requirements.in` | The direct dependencies of the code. Kaggle also uses them. | A person |
| `requirements-dev.in` | The tools for the local machines only (Kaggle CLI, pytest, ruff, ipykernel). | A person |
| `requirements.txt` | The lock for the local machines: all packages, with the PyTorch CPU build. | uv |
| `requirements-kaggle.txt` | The lock for Kaggle: the same versions, without PyTorch and without the tools. | uv |

### Make the local environment

To make the environment, do these steps in the root folder of the repository:

1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
2. Make the virtual environment with Python 3.13 (the same version as on Kaggle):

   ```bash
   uv venv --python 3.13 .venv
   ```

3. Install the locked packages:

   ```bash
   uv pip sync --python .venv requirements.txt --index-strategy unsafe-best-match
   ```

The flag `--index-strategy unsafe-best-match` is necessary because the lock also uses the PyTorch CPU index. `uv pip sync` removes all packages that are not in the lock. Thus the environment is the same as the lock.

If `requirements.txt` changes after a `git pull`, do step 3 again.

### Install OpenSpec

All team members use the same version of the OpenSpec CLI. The skills of OpenSpec call the command `openspec`.

1. Install Node.js 20.19 or a newer version.
2. Install the OpenSpec CLI:

   ```bash
   npm install -g @fission-ai/openspec@1.14.0
   ```

3. Check the version. The command must show `1.14.0`:

   ```bash
   openspec --version
   ```

To change the version of OpenSpec, change the version in step 2. Then run `openspec update` and commit the changed files.

### Install the packages on Kaggle

Kaggle has its own PyTorch GPU build. The CPU build from `requirements.txt` replaces it. Thus `run.py` installs only `requirements-kaggle.txt` from the clone of the repository:

```python
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)
```

This lock does not have PyTorch and the packages that only PyTorch needs (sympy, mpmath, networkx, setuptools). Thus the PyTorch of Kaggle stays. All other packages get the same versions as on the local machines. Write the version of PyTorch into the log of the run.

### Change a package

To add, remove or change a package, do these steps:

1. Change `requirements.in` or `requirements-dev.in`.
2. Make the lock for the local machines:

   ```bash
   uv pip compile requirements.in requirements-dev.in --universal --python-version 3.13 --index-strategy unsafe-best-match --emit-index-url -o requirements.txt
   ```

3. Make the lock for Kaggle from the first lock:

   ```bash
   uv pip compile requirements.in -c requirements.txt --universal --python-version 3.13 --index-strategy unsafe-best-match --no-emit-package torch --no-emit-package sympy --no-emit-package mpmath --no-emit-package networkx --no-emit-package setuptools -o requirements-kaggle.txt
   ```

4. Install the new lock (step 3 of "Make the local environment").
5. Commit the four files together.
6. Tell the team that the lock changed.

If a new version of PyTorch needs a new package, add this package to the `--no-emit-package` options in step 3.

Do not install a package with `pip install` or `uv pip install` into `.venv`. A package that is not in the lock makes the environments different.

## Code

- Write few comments. A comment tells why the code does a thing. Do not repeat what the code shows.
- Keep the code simple and clean.
- Put all logic in `src/`. Notebooks only import from `src/` and show results.
- Keep names in the code independent of the domain (`environment`, `task`, `tool`, not `jira_*`). The domain can change.
- Keep secrets (API keys, tokens) only in `.env`. Never commit `.env`.

## Experiments

The course grades a before/after measurement on the same test set. These rules keep the numbers correct.

- Freeze the test set at E1. Do not change `data/tasks/test/` after E1. If a change is necessary, run all variants again.
- Keep the train tasks and the test tasks separate. A test must check that no task is in both sets.
- Change one thing in each variant. Keep the test set and all other settings the same.
- Record the config, the model version, the commit hash and the results of each run.
- Report the time and the cost of a task next to its quality.
- The size of the model is not a variable in the grade. An improvement must come from the method, not from a larger model.

## Compute

- The local machines have no GPU.
- Run short tests locally on the CPU.
- Run long computations on Kaggle (GPU or CPU). Examples: train a model, run a full evaluation.
- The repository is the project. Thus `run.py` clones the full repository from `main`. It does not use a sparse checkout or a project folder, as the examples in `KAGGLE.md` do.
- On Kaggle, install only `requirements-kaggle.txt` (see "Install the packages on Kaggle").

## Text in files (Simplified Technical English)

Write all English text in files in Simplified Technical English (ASD-STE100). This applies to the README file, reports, comments, docstrings, commit messages and pull request descriptions. It does not apply to names in code, to text that you quote, or to messages to the user in the conversation.

1. Use the active voice. Use the passive voice only when the agent is not known or not important.
2. Write an instruction in 20 words or fewer. Write a description sentence in 25 words or fewer.
3. Put one idea in each sentence.
4. Use the same word for the same thing every time. Do not use synonyms for variety.
5. Do not use idioms or slang. Technical terms (LoRA, GRPO, MCP, SFT) are correct. Use the same form every time.
6. Use simple, common words. Use a single verb, not a phrasal verb: "find", not "find out".
7. Do not use contractions such as "don't" or "it's".
8. Do not put more than three nouns in a row.
9. Do not use the "-ing" form as a verb.
10. Use a vertical list when a sentence has more than three items.
11. Start a procedure with its goal. Then give the steps as a numbered list, with one action in each step.

Use these rules for new text and for text that you change. Do not rewrite old text only to obey these rules.
