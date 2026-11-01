# Project plan

## Goal

We train a small open language model (approximately 1.7B parameters) to do tasks in a project management system. The model gets an instruction in Polish, for example "Przenieś otwarte błędy z etykietą frontend do następnego sprintu i przypisz je Ani". It does the task with tools from an MCP server.

The research question: can a small local model, fine-tuned for one task, come near a large API model at a much lower cost and without data that goes outside the company?

## System

- We make a simulator of Jira with synthetic data: issues, persons and sprints. There is no personal data.
- An MCP server gives the tools of the simulator to the model.
- A program checks each task automatically. It compares the final state of the board with the expected state.
- The domain can change. Thus the names in the code are independent of the domain.

## Milestones

| Milestone | Date | Deliverable |
|---|---|---|
| E1 | 2026-11-16 | The base system operates: the simulator, the small model that uses the tools with a prompt only, a test set of some hundreds of tasks with the expected results, and the baseline score. |
| E2 | 2026-12-07 | Fine-tuning of the model (LoRA) on examples of correct solutions. The score before and after on the same test set. The test set is separate from the training data. |
| E3 | 2026-12-21 | More training with reinforcement learning: the model gets a reward for a correct task. A comparison with E2. A test on real Jira (free cloud plan) that the model did not see in training. |
| Demo Day | 2027-01-11 | A demo of the system on a real Jira board, and the before/after results. |

## Comparison

A large API model is only a reference point. The improvement must come from the method, not from a larger model.