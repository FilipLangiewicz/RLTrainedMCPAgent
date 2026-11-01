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
