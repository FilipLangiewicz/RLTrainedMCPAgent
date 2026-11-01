# RLTrainedMCPAgent

We train a small open language model to do multi-step tasks in a project management system with MCP tools. The model gets an instruction in Polish and uses the tools of a Jira simulator to do the task. It learns first from correct examples (SFT), then from a reward for a correct task (RL).

The project plan is in `docs/project.md`. The rules for the team and the setup of the environment are in `AGENTS.md`.
