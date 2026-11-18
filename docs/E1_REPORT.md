# E1: Base system, test set and baseline

## Project

We train a small open language model to do tasks in Jira. The model gets an instruction in Polish, for example:

> Proszę przypisać Michałowi wszystkie nieprzypisane bugi z etykietą security.

The model does the task with the tools of an MCP server. Some instructions and issues also have English words.

The research question: can a small local model, with fine-tuning for one task, come near a large API model? The small model has a much lower cost, and the data stays inside the company.

## System

```mermaid
flowchart LR
    B["Board of the task<br/>(initial state)"] -->|copy| SIM["Jira simulator"]
    P["System prompt"] --> A["Agent loop"]
    I["Instruction"] --> A
    A <-->|"messages,<br/>tool schemas"| M["Model"]
    A <-->|"tool calls<br/>and results"| S["MCP server<br/>(14 tools)"]
    S <--> SIM
    B -->|initial board| V["Verifier"]
    SIM -->|final board| V
    A -->|final answer| V
    X["Expected result"] --> V
    V --> G["correct /<br/>correct_refusal /<br/>incorrect"]
```

1. Each task gets a new copy of its board in the simulator: a Jira project with issues, persons and sprints.
2. The agent loop gives the system prompt, the instruction and the tool schemas to the model.
3. The model sends tool calls. The MCP server runs them on the simulator and returns the results.
4. The loop stops when the model gives an answer without a tool call, or when a limit stops it.
5. The verifier compares the initial board with the final board. It checks these changes and the answer against the expected result.

The 14 tools have the names, the schemas and the result format of `mcp-atlassian` 0.23.1, an MCP server for real Jira. We recorded 43 calls on a Jira Cloud site. A test runs these calls on the simulator and compares the results.

## Data

All data is synthetic, with no personal data. The boards of the three sets belong to different invented companies. No board, instruction, issue or person occurs in two sets.

| Property | Test | Train | Validation |
|---|---|---|---|
| Tasks | 200 | 1000 | 120 |
| Boards (Jira projects) | 5 | 25 | 3 |
| Companies | 1 | 5 | 1 |
| Jira issues on the boards | 200 | 976 | 117 |
| Authors of instructions | 16 | 75 | 9 |
| `easy` tasks | 72 | 375 | 45 |
| `multi_step` tasks | 103 | 500 | 60 |
| `refusal` tasks | 25 | 125 | 15 |

A task is one instruction for the model. A Jira issue is a ticket on a board. Each board has 40 tasks. The test boards have 40 issues each, and the other boards have 38 to 42 issues.

- `easy`: the instruction gives the issue key, and the task has one operation.
- `multi_step`: the model must find the issue with a search, or it must do more than one operation.
- `refusal`: no tool can do the request, or the request is not clear. The correct answer is a refusal.

Each task has an instruction, an expected result and a reference solution. The reference solution of each task passes the verifier. All sets have the same 8 categories.

- The test set is for the measurement only. Both team members did a review of it, and it is frozen.
- The train set is for SFT and RL.
- The validation set is for the selection of the training settings.

## Models and settings

The local models are six open models of three families: Qwen3.5 (2B, 4B), Bielik v3 (1.5B, 4.5B) and Gemma 4 (E2B, E4B). Four API models are the reference point: Opus 5.5, Sonnet 5.5, Haiku 5.5 and Gemini 4 Argon.

All models use the same system prompt (`v3`) and no training. The local models use greedy decoding on a Kaggle T4 GPU. The API models use temperature 0. The agent stops after 25 tool calls.

## Baseline results

### How to read the score

The model gets 1 point for a task with the grade `correct` or `correct_refusal`. It gets 0 points for the grade `incorrect`. The score is the sum of the points divided by the number of tasks. Thus the score 0.500 means that the model solved half of the tasks.

- `correct`: the board has exactly the expected changes, or the answer has the expected information.
- `correct_refusal`: the task needs a refusal, the answer starts with `ODMOWA:`, and the board does not change.
- `incorrect`: all other results.

### Ranking

![Ranking of the models](../data/results/baseline/figures/6-ranking.png)

The line on each bar is the Wilson 95% interval of the score. The formula uses only the score and the number of tasks (200). It treats each task as an independent trial.

- The interval shows how much the score can change on another set of similar tasks.
- If two lines overlap, the difference can be noise.
- All models solve the same tasks. A paired test of two models can find a difference that this interval hides.

### Local models and external models

The local models run on Kaggle GPUs. The external models run through the service of a provider. The figure shows the mean score of each group. The line on each bar shows the lowest and the highest model of the group.

![Score of the groups by task type](../data/results/baseline/figures/1-groups-by-type.png)

### Score by task type

| Model | Group | All | `easy` | `multi_step` | `refusal` |
|---|---|---|---|---|---|
| Opus 5.5 | external | 0.980 | 1.000 | 0.971 | 0.960 |
| Gemini 4 Argon | external | 0.980 | 0.986 | 0.971 | 1.000 |
| Sonnet 5.5 | external | 0.945 | 0.986 | 0.913 | 0.960 |
| Haiku 5.5 | external | 0.785 | 0.750 | 0.786 | 0.880 |
| Gemma 4 E4B | local | 0.325 | 0.556 | 0.097 | 0.600 |
| Gemma 4 E2B | local | 0.305 | 0.458 | 0.058 | 0.880 |
| Qwen3.5-4B | local | 0.265 | 0.472 | 0.107 | 0.320 |
| Bielik 4.5B | local | 0.120 | 0.319 | 0.010 | 0.000 |
| Qwen3.5-2B | local | 0.120 | 0.264 | 0.019 | 0.120 |
| Bielik 1.5B | local | 0.050 | 0.139 | 0.000 | 0.000 |

![Score by task type for each model](../data/results/baseline/figures/2-types-by-model.png)

### Score by category

The category tells what the user wants. Each task has one category. The number of tasks is in brackets.

| Category | Meaning |
|---|---|
| `bulk` (20) | The same change for many issues of a filter. |
| `create` (25) | A new issue. |
| `log` (25) | A comment or a worklog. |
| `query` (30) | Information only. The board does not change. |
| `refusal` (25) | A request that the model must refuse. |
| `sprint` (25) | A change of the sprint of an issue, or a move to the backlog. |
| `update` (30) | One change of one issue, for example the assignee or the status. |
| `workflow` (20) | Different operations in one task, for example close, log and comment. |

| Model | `bulk` | `create` | `log` | `query` | `refusal` | `sprint` | `update` | `workflow` |
|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 1.000 | 1.000 | 1.000 | 0.967 | 0.960 | 1.000 | 0.967 | 0.950 |
| Gemini 4 Argon | 1.000 | 1.000 | 0.960 | 0.967 | 1.000 | 1.000 | 0.967 | 0.950 |
| Sonnet 5.5 | 0.950 | 0.960 | 0.920 | 0.933 | 0.960 | 1.000 | 1.000 | 0.800 |
| Haiku 5.5 | 0.900 | 0.000 | 0.800 | 0.967 | 0.880 | 0.960 | 1.000 | 0.700 |
| Gemma 4 E4B | 0.150 | 0.000 | 0.280 | 0.567 | 0.600 | 0.320 | 0.433 | 0.100 |
| Gemma 4 E2B | 0.050 | 0.000 | 0.320 | 0.400 | 0.880 | 0.240 | 0.367 | 0.050 |
| Qwen3.5-4B | 0.050 | 0.080 | 0.360 | 0.333 | 0.320 | 0.360 | 0.400 | 0.100 |
| Bielik 4.5B | 0.000 | 0.000 | 0.360 | 0.300 | 0.000 | 0.160 | 0.067 | 0.000 |
| Qwen3.5-2B | 0.000 | 0.000 | 0.240 | 0.267 | 0.120 | 0.120 | 0.133 | 0.000 |
| Bielik 1.5B | 0.000 | 0.000 | 0.080 | 0.200 | 0.000 | 0.080 | 0.000 | 0.000 |

![Score by category](../data/results/baseline/figures/3-categories-heatmap.png)

### Main points

- The best local model (Gemma 4 E4B, 0.325) is far below the weakest external model (Haiku 5.5, 0.785). The gap is 0.46.
- The gap is largest for `multi_step`. The best local score is 0.107. Opus 5.5 and Argon have 0.971.
- No local model solves the `create` category. The best score is 0.080.
- Haiku 5.5 also has the score 0 for `create`. In 23 of 25 `create` tasks it made no tool call. It asked the user for the project key.
- Opus 5.5 and Argon have the same score. Argon needs about 9 times more task time and costs more.
- The high `refusal` score of the Gemma models is not a good result. They refuse too often (see the report of each model).
- The external models show that the tasks are possible. The scores 0.945 and 0.980 are the target for SFT and RL.

### Behavior, tokens and cost

![Score and cost of the external models](../data/results/baseline/figures/4-score-vs-cost.png)

![Failures of the local models](../data/results/baseline/figures/5-local-failures.png)

| Model | Task time (s) | No call | Loop or limit | Input tokens | Output tokens | Cost (USD) |
|---|---|---|---|---|---|---|
| Opus 5.5 | 1219 | 6 | 0 | 5 599 109 | 93 340 | 4.93 |
| Gemini 4 Argon | 11276 | 1 | 0 | 4 397 528 | 71 436 | 5.60 |
| Sonnet 5.5 | 806 | 9 | 0 | 5 610 669 | 77 762 | 3.02 |
| Haiku 5.5 | 757 | 34 | 0 | 5 005 711 | 124 154 | 0.16 |
| Gemma 4 E4B | 2998 | 73 | 0 | 1 816 652 | 12 986 | local |
| Gemma 4 E2B | 1818 | 75 | 1 | 1 629 697 | 13 246 | local |
| Qwen3.5-4B | 10431 | 25 | 72 | 3 812 523 | 105 359 | local |
| Bielik 4.5B | 11851 | 16 | 95 | 2 709 076 | 100 765 | local |
| Qwen3.5-2B | 12352 | 17 | 124 | 2 248 680 | 220 032 | local |
| Bielik 1.5B | 3618 | 4 | 39 | 2 285 610 | 79 446 | local |

- "Task time" is the sum of the times of the 200 tasks, as if the tasks ran one after another.
- "No call" counts the tasks with no tool call.
- "Loop or limit" counts the tasks that stop at `loop_same`, `loop_errors` or `max_steps`.
- "Input tokens" is the sum for all calls of all tasks. Each call sends the full history again, so this number is much larger than the output.
- The local models have no cost in USD, because we do not pay for the tokens of these models.
- The tokens of different models are not the same unit. Each model has its own tokenizer.

## Main errors of the local models

- The model makes up a project key, a board id or a transition id. It does not read them from a tool.
- The model asks the user for an issue key. It does not search for the issue.
- After an empty search result, the model does not search again with another word.
- The model writes invalid JQL.
- The model refuses a possible task, or it does not refuse an impossible task.
