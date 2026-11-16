# Design

## Context

- `docs/RL_METHODS.md` and the comment of idm-pro-047 give the method, the reward, the GPU layouts and the measurements of jobs 41 to 61.
- The agent loop (`src/agent.py`) keeps the parsed form of each model turn in the messages. Before the next turn, the family renders all messages again. Thus the rendered tokens are not always the tokens that the model sampled. Examples:
  - Bielik writes text after `</tool_call>`. The parser removes this text and writes the call again as JSON.
  - Qwen3.5 can write a parameter in a different form than `format_calls` writes it.
- The GRPO ratio needs the log-probability of the sampled tokens. A loss on the rendered tokens trains the model on text that it did not write.
- `GRPOTrainer` of TRL 1.17 accepts a custom `rollout_func`, but only one sequence for each rollout. Our rollouts can need more than one sequence (see Decision 2).
- `AsyncGRPOTrainer` of TRL 1.18 can split a rollout. But it loads the flash-attn3 kernel and uses bf16. A T4 has neither.
- Kaggle gives 2x T4 (15 GB each, fp16 only), 12 hours for each session and about 30 GPU hours each week. A kernel with the status ERROR loses its full output.

## Goals / Non-Goals

**Goals:**

- One code path for all six models. Only the YAML config changes between models.
- The loss uses only tokens that the model sampled, with the log-probabilities of the sampler.
- The evaluation on the test set stays the same as for the baselines.
- A run of many jobs gives the same result as one long run, with the exception of the random state of the sampler.
- All parts that do not need a model have local tests. The parts that need a model have smoke tests on Kaggle.

**Non-Goals:**

- The selection of the RL settings and of the models (idm-pro-049).
- A speed optimization past the measured layouts, for example the packed trees of TRL 1.18 or a shorter form of tool results.
- More than one node or more than two GPUs.

## Decisions

### 1. Our own GRPO loop, not the trainer of TRL

The loop uses PyTorch, PEFT (LoRA), transformers (the model), vLLM (generation) and the OpenAI client (requests to vLLM). Our code has only the parts that these libraries do not give:

- the rollouts on the simulator;
- the advantage and the loss (about 40 lines);
- the loop of steps and the checkpoints.

Alternatives:

- `GRPOTrainer` with `rollout_func`: it needs one sequence for each rollout. Thus it trains on the rendered tokens, or it cannot take our rollouts. Rejected.
- `AsyncGRPOTrainer` (TRL 1.18): it needs flash-attn3 and bf16. Rejected for the T4.
- A patch of the TRL trainer: the patch must follow each change of TRL. A short loop of our own is easier to read and to test.

TRL stays in the lock, because SFT can use it. `docs/RL_METHODS.md` gets a note: the method of idm-pro-047 stays, and only the trainer changes.

### 2. Samples from the exact tokens of each turn

The generation engine records each turn of a rollout:

- the token ids of the prompt;
- the token ids that the model sampled;
- the log-probability of each sampled token from the sampler.

The trainer makes the samples from these records:

- If the prompt of turn k+1 starts with the prompt and the output of turn k, the two turns become one sample. The tokens between them (tool results, template tokens) get the mask 0.
- If not, turn k+1 starts a new sample.
- All samples of a rollout get the advantage of the rollout.

Thus a family with a stable template gives one sample for each rollout, and Bielik gives one sample for each turn. The cost is a longer backward pass for a family with many samples. The result is correct for all families.

Alternative: render the full conversation one time and train on the model positions (as `src/rl_probe.py` did). Rejected, because these tokens are not the sampled tokens.

`src/rl/tokens.py` has these functions. It also has a function that converts a full conversation to token ids and a mask of the model tokens. SFT can use this function (see the comment in idm-pro-048).

### 3. No change of the agent loop

The engine gives a new model object for each rollout. This object has the interface of the model layer (`generate(messages, tools)`) and records the turns. The agent loop calls it as any other model. Thus the rollouts of an RL run and the evaluation use the same loop, the same parsers and the same prompt.

The limits of an RL run are settings of the run:

- `agent.max_steps`, `agent.loop_limit` and `agent.error_limit` go to the agent loop. They can be tighter than in the evaluation.
- `rl.max_context_tokens`: if a prompt is longer, the model object raises an error. The agent loop stops the rollout with the stop reason `error`. The rollout gets the reward 0. Its earlier turns stay in the batch.

The evaluation configs do not have these settings. Thus the test set keeps its limits.

### 4. Advantage and loss

For each group of rollouts of one task:

- advantage = reward − mean reward of the group (Dr. GRPO, no division by the standard deviation);
- a group with equal rewards has the advantage 0 for all rollouts. The step drops it before the backward pass and records its share.

For each model token t of a sample:

- ratio = exp(logp_trainer(t) − logp_sampler(t));
- loss(t) = −min(ratio · A, clip(ratio, 1 − `clip_low`, 1 + `clip_high`) · A).

The loss of a step is the sum of loss(t) over all model tokens of the step. The step divides this sum by the number of these tokens (the token-level loss of DAPO). There is no KL term. The defaults are `clip_low: 0.2` and `clip_high: 0.28` (DAPO).

The step does one optimizer update. It accumulates the gradients of one sample at a time, without a pad of the sequences. If the gradient is not finite, the step does no update and records the event.

The trainer computes the log-probabilities in chunks of `rl.logprob_chunk` positions. It computes logits only at the positions of model tokens. A Qwen vocabulary of 248k tokens otherwise needs gigabytes for the logits.

The partial reward (variant B of `docs/RL_METHODS.md`) is the setting `rl.reward: partial`. The default is `binary`.

### 5. Generation engines

Each engine has the same interface:

- `start()`;
- `model_for_rollout()`: a new model object (Decision 3);
- `load_adapter(path)`;
- `stop()`.

`vllm` engine (default for `bielik` and `qwen3.5`):

- `vllm serve` runs from a separate environment on GPU 0. The trainer runs on GPU 1.
- The server gets each new LoRA adapter at run time, without a restart (measured below 1 s).
- Requests send the token ids of the prompt. Thus the server does not add a second BOS token.
- The server returns the log-probability of each sampled token.
- Gemma 4 gets the T4 patch of the attention tile (from `src/rl_probe.py`).

`transformers` engine (default for `gemma4`):

- Two copies of the model, one on each GPU. Each copy samples one half of the rollouts and computes the gradients of its half.
- The gradients of the LoRA weights of copy 0 are added to copy 1. Copy 1 does the optimizer update. Then copy 0 gets the new LoRA weights.
- The LoRA weights have about 0.5% of the parameters. Thus the sum and the copy take less than 1 s.
- The sampler computes the log-probabilities from the scores of `generate`.

Alternative for the two copies: `torch.distributed` with DDP. Rejected: two processes and a process group give more failure modes on Kaggle, and the gain is small for LoRA.

The config selects the engine with `engine.name`. A run with the `vllm` engine needs `VLLM_PYTHON`, the path of the Python in the vLLM environment.

### 6. Overlap of generation and update (vLLM)

With `engine.overlap: true` (the default for `vllm`), vLLM samples the rollouts of step k+1 while the trainer does the update of step k. Thus the sampler is at most one update behind the trainer. The clip of the ratio (Decision 4) covers this difference. With `engine.overlap: false`, the sampler always uses the newest adapter. The `transformers` engine has no overlap, because the same GPUs sample and train.

### 7. Start weights and the new adapter

- `model.path` gives the base weights.
- `model.adapters` (optional) gives a list of LoRA adapters, for example the SFT adapter. The loader merges them into the base weights in the order of the list.
- A folder without `adapter_config.json` has full weights and loads directly.
- For the `vllm` engine, the trainer writes the merged weights one time to `/kaggle/temp/merged`. vLLM serves this folder.
- The RL adapter is a new LoRA adapter. Defaults: rank 16, alpha 32, dropout 0. The target modules are the seven linear layers of attention and MLP (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`). vLLM accepts adapters on these modules. Vision and audio modules get no adapter.

The model layer gets the same `model.adapters` setting (see the delta of `model-layer`). Thus the evaluation runs a model after SFT or after RL with the base weights and the list of adapters.

### 8. Precision and memory

- Weights in fp16, because the T4 has no bf16. The LoRA weights and the loss are in fp32. The forward pass uses autocast fp16.
- The backward pass computes the activations again (gradient checkpoints), so that long sequences fit in memory.
- For `gemma4`, the per-layer lookup tables (PLE) stay in CPU memory (as in the probe).
- The Kaggle job removes torchao before the import of PEFT.

### 9. Checkpoints and long runs

A checkpoint is a folder `checkpoints/step-<N>/` in the output folder. It has:

- the LoRA adapter;
- the state of the optimizer and of the learning-rate schedule;
- the step, the epoch and the position in the task order;
- the random states;
- a hash of the config.

The run writes a checkpoint every `rl.save_every` steps (default 25) and keeps the last `rl.keep_checkpoints` (default 2). The command `--resume <folder>` continues from a checkpoint. The run stops if the config differs from the config of the checkpoint. The settings of the run length (`rl.steps`, `rl.deadline_hours`) can differ.

After `rl.deadline_hours` (default 11), no new step starts. The run writes a checkpoint and stops. The top level of the run catches each error. It writes the error into `status.json`, writes a checkpoint if possible and exits with code 0. Thus Kaggle keeps the output of a failed run.

A next job adds the output of the previous job as a kernel source and gives its last checkpoint to `--resume`.

### 10. Tasks, epochs and validation

- The run uses the split `train`. A config with the split `test` stops the run, except in measure mode.
- Each epoch is a new random order of the train tasks (seed + epoch number). Each step takes `rl.tasks_per_step` tasks and samples `rl.group` rollouts for each task.
- Every `rl.eval_every` steps, the run does the validation: one greedy rollout for each of `rl.eval_tasks` validation tasks, with the limits of the run. The run records the score. It keeps the adapter with the best score in `best/`.

### 11. Measure mode

`rl.mode: measure` samples `rl.group` rollouts for each of `rl.tasks` tasks and does no update. It writes the statistics of the groups: the mean reward, the share of groups with mixed rewards, the times and the token counts. The second probe after SFT uses this mode on the train or the validation split. The test split is allowed only in this mode, only for the cost measurement (rule of idm-pro-047).

### 12. Records of a run

The output folder gets small files only:

- `run.json`: the full config, the git commit, the versions of PyTorch, transformers, PEFT and vLLM, the GPU and the start time;
- `metrics.jsonl`: one line for each step and for each validation;
- `rollouts.jsonl`: one line for each rollout without the messages (task id, reward, stop reason, steps, tokens, time);
- `status.json`: `running`, `complete`, `deadline` or `error`, with the last step;
- `checkpoints/`, `best/` and `final/` with the adapters.

A line of `metrics.jsonl` has:

- the step, the epoch and the times of generation, update and step;
- the mean reward and the mean partial reward;
- the share of groups with mixed rewards;
- the loss and the gradient norm;
- the share of clipped tokens;
- the mean and the maximum difference of the sampler and the trainer log-probabilities;
- the numbers of samples and of model tokens.

### 13. Config

The config is a YAML file in the folder of a job, as for the evaluation. It has the sections `model`, `agent`, `engine` and `rl`. `src/rl/config.py` has the defaults. An unknown key stops the run, because a typo must not give a silent default.

Main keys of `rl` and their defaults:

| Key | Default | Source |
|---|---|---|
| `mode` | `train` | |
| `steps` | 200 | idm-pro-047 estimate |
| `epochs` | 1 | |
| `tasks_per_step` | 8 | probe |
| `group` | 8 | probe |
| `learning_rate` | 1e-5 | selected in idm-pro-049 |
| `lora_rank` / `lora_alpha` | 16 / 32 | idm-pro-047 |
| `loss_type` | `dapo` | idm-pro-047 |
| `clip_low` / `clip_high` | 0.2 / 0.28 | DAPO |
| `reward` | `binary` | idm-pro-047 |
| `max_context_tokens` | 8192 | probe |
| `save_every` | 25 | idm-pro-047 |
| `eval_every` / `eval_tasks` | 25 / 40 | |
| `deadline_hours` | 11 | Kaggle limit |
| `temperature` | 1.0 | probe |

`loss_type` has only the value `dapo` in this change. The key exists so that a later variant does not change the config form.

### 14. Files

| File | Reason |
|---|---|
| `src/rl/__init__.py` | Makes `src/rl` a package. Empty. |
| `src/rl/config.py` | Loads the YAML, adds the defaults, checks the keys. |
| `src/rl/tokens.py` | Turn records, samples with masks, the conversation function for SFT. |
| `src/rl/engines.py` | The `vllm` and `transformers` engines and the model object for one rollout. |
| `src/rl/rollouts.py` | Runs the groups of rollouts, computes the reward and the group statistics. |
| `src/rl/grpo.py` | Advantage, log-probabilities in chunks, loss. No model code. |
| `src/rl/policy.py` | Loads the trainer model, merges the start adapters, adds the RL adapter, moves the PLE tables. |
| `src/rl/checkpoint.py` | Writes and reads the checkpoints. |
| `src/rl/train.py` | The command `python -m src.rl.train <config> --output <folder> [--resume <folder>]`, the loop of steps, the deadline, the records. |
| `tests/test_rl.py` | The local tests. |

`src/rl_probe.py` goes away. Its vLLM server code, the T4 patch and the PLE code move to `src/rl/engines.py` and `src/rl/policy.py`.

### 15. Tests

Local tests (no model, no GPU):

- the config: defaults, an unknown key, the test split in train mode;
- the samples: merge of turns with a stable prefix, a new sample after a changed prefix, the masks. A small fake tokenizer in the test gives the token ids;
- the advantage, the group filter and the loss on small tensors, also the clip and the token-level mean;
- a checkpoint write and read with a small `torch.nn.Linear`;
- the reward and the group statistics with the `scripted` model and the simulator.

Kaggle smoke tests run on the train and the validation splits, on GPU. Each test does all parts of a real run:

- a few steps;
- a validation;
- a checkpoint and a second job that continues from it;
- the final adapter;
- a short evaluation of the adapter with `model.adapters`.

The order is from the fastest model to the slowest: Bielik 1.5B, Gemma 4 E2B, Gemma 4 E4B, Bielik 4.5B, Qwen3.5-2B, Qwen3.5-4B. While the code changes, a test runs on one model, and a failure stops the next tests. The acceptance is one run of all six models on the final commit. Each smoke test must take less than about 30 minutes. Thus the test of Qwen3.5-4B uses few tasks, a small group and a short context limit.

## Risks / Trade-offs

- [Bielik gives one sample for each turn, so its backward pass repeats the history] → The measured backward pass of Bielik is the shortest. The record of the number of samples shows the real cost.
- [The custom loop can have a bug that TRL does not have] → Local tests of the loss on known numbers. The records show the difference of the log-probabilities and the share of clipped tokens in each step.
- [fp16 can give an infinite gradient] → The step skips the update and records it. LoRA weights and the loss stay in fp32.
- [vLLM has a different version or behavior on Kaggle] → Each job installs a fixed vLLM version (the version of jobs 51 to 61) and records it in `run.json`.
- [The KV cache of Qwen3.5-4B holds only about 15 rollouts in vLLM] → The concurrency is a setting of `engine`. The smoke test uses small numbers.
- [The merged weights for vLLM need disk space] → `/kaggle/temp` has enough space for one model of up to 9 GB. The run deletes the folder at the end.
- [A Kaggle session stops without a warning] → A checkpoint every 25 steps. A loss of at most 25 steps.
- [Loss of the overlap of TRL-like libraries] → Decision 6 keeps the overlap of the probe for vLLM.

## Migration Plan

1. Add `src/rl/` and its tests. Remove `src/rl_probe.py`.
2. Run the Kaggle smoke tests (see Decision 15).
3. Update `docs/RL_METHODS.md`, `jobs/JOBS.md` and `docs/WORKLOG.md`.

To roll back, revert the branch. No data and no evaluation result changes.

## Open Questions

- The values of `learning_rate`, `steps` and `group` for the real runs. idm-pro-049 selects them. The defaults above are only start values.
