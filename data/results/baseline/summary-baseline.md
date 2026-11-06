# Summary of the baselines

This file compares the six baselines. Each model has its own report in this folder, with the Why of each task.

All runs use the same setup:

- the 200 tasks of the frozen test set: 72 `easy`, 103 `multi_step` and 25 `refusal`
- the prompt `v3`, a prompt only, with no training
- the limits for each task: 25 calls, 3 equal calls in a row and 5 errors in a row
- the same code in `src/`, the same library versions and Kaggle T4 GPUs

## Result

The score is the part of the tasks with the grade `correct` or `correct_refusal`.

| Model | Score | Tasks | `easy` | `multi_step` | `refusal` | Time (s) |
|---|---|---|---|---|---|---|
| Gemma 4 E4B | 0.325 | 65 | 0.556 | 0.097 | 0.600 | 2999 |
| Gemma 4 E2B | 0.305 | 61 | 0.458 | 0.058 | 0.880 | 936 |
| Qwen3.5-4B | 0.265 | 53 | 0.472 | 0.107 | 0.320 | 5439 |
| Bielik 4.5B | 0.120 | 24 | 0.319 | 0.010 | 0.000 | 6647 |
| Qwen3.5-2B | 0.120 | 24 | 0.264 | 0.019 | 0.120 | 6320 |
| Bielik 1.5B | 0.050 | 10 | 0.139 | 0.000 | 0.000 | 1882 |

## Score by category

| Model | `bulk` | `create` | `log` | `query` | `refusal` | `sprint` | `update` | `workflow` |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 E4B | 0.150 | 0.000 | 0.280 | 0.567 | 0.600 | 0.320 | 0.433 | 0.100 |
| Gemma 4 E2B | 0.050 | 0.000 | 0.320 | 0.400 | 0.880 | 0.240 | 0.367 | 0.050 |
| Qwen3.5-4B | 0.050 | 0.080 | 0.360 | 0.333 | 0.320 | 0.360 | 0.400 | 0.100 |
| Bielik 4.5B | 0.000 | 0.000 | 0.360 | 0.300 | 0.000 | 0.160 | 0.067 | 0.000 |
| Qwen3.5-2B | 0.000 | 0.000 | 0.240 | 0.267 | 0.120 | 0.120 | 0.133 | 0.000 |
| Bielik 1.5B | 0.000 | 0.000 | 0.080 | 0.200 | 0.000 | 0.080 | 0.000 | 0.000 |

## Behavior of the models

The column "No call" counts the tasks with no tool call. The column "False ODMOWA" counts the tasks that do not need a refusal, but have an answer that starts with ODMOWA.

| Model | Answer | `loop_same` | `loop_errors` | `max_steps` | Error | No call | False ODMOWA | Most calls in a task |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 E4B | 200 | 0 | 0 | 0 | 0 | 73 | 61 | 7 |
| Gemma 4 E2B | 199 | 0 | 1 | 0 | 0 | 75 | 58 | 6 |
| Qwen3.5-4B | 128 | 67 | 4 | 1 | 0 | 25 | 6 | 25 |
| Bielik 4.5B | 104 | 28 | 57 | 10 | 1 | 16 | 4 | 25 |
| Qwen3.5-2B | 76 | 85 | 38 | 1 | 0 | 17 | 4 | 25 |
| Bielik 1.5B | 161 | 15 | 17 | 7 | 0 | 4 | 17 | 25 |

## Main points

- No model does the task well without training. The best score is 0.325.
- The gap is in `multi_step` tasks: the best score is 0.107. The `create` category has a score of 0 for five models and 0.080 for Qwen3.5-4B.
- 107 of the 200 tasks have no correct solution from any model: 84 `multi_step`, 22 `easy` and 1 `refusal`. All models together solve 93 tasks.
- The two Gemma models refuse too often. They give a false ODMOWA in 61 and 58 of the 175 other tasks. Thus their high `refusal` score does not show a good decision.
- Qwen3.5-4B has the highest `multi_step` score and only 6 false ODMOWA, but 67 of its tasks stop at `loop_same`.
- The Bielik models and Qwen3.5-2B often stop at a limit: 95, 39 and 124 tasks. The models use invented values and repeat a failed call.

## Limits of these numbers

- A small difference can be noise. Gemma 4 E4B and Gemma 4 E2B differ by 4 tasks, but 16 tasks are correct only for E4B and 12 only for E2B.
- In Bielik 4.5B, `test-028` stopped with a GPU memory error after 14 calls. Its grade is `incorrect`. The model made no correct change before this error.
- Gemma 4 E4B ran with one process, and the other models ran with two processes. Thus the times do not give an exact comparison of speed.
- No large API model has run on this test set. Thus these numbers do not show the highest score that the tasks permit.
