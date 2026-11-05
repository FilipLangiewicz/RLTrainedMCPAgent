# Jobs

All Kaggle jobs of the project. The full rules are in `KAGGLE.md`.

## Table

Status values: to run, waiting for another job, queued, running, complete, failed, cancelled. The status cell has only one of these values, because `wait.sh` changes it. Put results into the comment.

| Date | Job | Folder | Link | Comment | Status |
|---|---|---|---|---|---|
| 2026-11-01 | baseline-v1 | `2026-11-01_01_baseline-v1` | [rltrainedmcpagent-baseline-v1](https://www.kaggle.com/code/mikoajrowicki/rltrainedmcpagent-baseline-v1) | Baseline for E1: `Qwen/Qwen3-1.7B`, `float16`, prompt `v1`, the test set (200 tasks), one half of the tasks on each GPU. Result: score 0.205 (correct 0.055, correct refusal 0.150). `easy` 0.157, `multi_step` 0.000, `refusal` 1.000. The model refuses 151 of 170 possible tasks without a tool call. Mean time 3.5 s for each task, 399 s for the job. | complete |
| 2026-11-05 | weights-qwen3-5-2b | `2026-11-05_02_weights-qwen3-5-2b` | [rltrainedmcpagent-weights-qwen3-5-2b](https://www.kaggle.com/code/combainsidm/rltrainedmcpagent-weights-qwen3-5-2b) | Download of the weights of `Qwen/Qwen3.5-2B` on a CPU kernel. The output has the folder `qwen3.5-2b/` with `manifest.json` (commit and SHA-256 of each file). Next step: make a private Kaggle Model from the output. Version 1: the output also had the folder `.cache`. Version 2 removes it. | complete |
