# Tasks

## 1. Config and samples

- [ ] 1.1 Add `src/rl/__init__.py` and `src/rl/config.py`: the sections `model`, `agent`, `engine` and `rl`, the defaults of design Decision 13, a stop on an unknown key, a stop on the split `test` in train mode. Also stop if `rl.max_context_tokens` plus `model.max_new_tokens` is larger than `rl.max_sample_tokens`. Verify with tests in `tests/test_rl.py`.
- [ ] 1.2 Add `src/rl/tokens.py`: the turn record, the samples with masks from the turns, and the conversation function for SFT. A merged sample longer than `rl.max_sample_tokens` becomes one sample for each turn. Verify with tests that use a small fake tokenizer: stable prefix, changed prefix, masks, the length limit.

## 2. Reward and loss

- [ ] 2.1 Add `src/rl/rollouts.py`: the run of groups of rollouts with a thread pool, the reward (`binary` and `partial`), the group statistics. Verify with tests that use the `scripted` model and the simulator, also the reward -0.2 for a write in a refusal task.
- [ ] 2.2 Add `src/rl/grpo.py`: the advantage, the group filter, the log-probabilities in chunks, the clipped token-level loss. Verify with tests on small tensors: known loss values, the clip, equal weight of all tokens, the drop of a group with equal rewards.

## 3. Model, engines and checkpoints

- [ ] 3.1 Add `model.adapters` to the `transformers` backend in `src/models.py`: merge in the order of the list, record the list, stop on an adapter of another base model. Verify with a test of the config check and of the record (no model load).
- [ ] 3.2 Add `src/rl/policy.py`. It loads the trainer model in fp16 and merges the start adapters. It adds the new RL adapter and the gradient checkpoints. It keeps the PLE tables of `gemma4` in CPU memory. Move the PLE code from `src/rl_probe.py`. Verify the config of the RL adapter with a test that needs no model.
- [ ] 3.3 Add `src/rl/engines.py` with these parts:
  - the engine interface;
  - the model object for one rollout, which records the turns and checks `rl.max_context_tokens`;
  - the `vllm` engine: server, T4 patch, adapter load, log-probabilities;
  - the `transformers` engine: two copies, sum of the LoRA gradients.

  Move the server code from `src/rl_probe.py`. Verify the turn records and the context limit with a fake engine in a test.
- [ ] 3.4 Add `src/rl/checkpoint.py`: write and read a checkpoint, keep all adapters and the optimizer state of the last N, compare the config hash without the keys of the run length. Verify with a test that writes and reads a checkpoint of a small `torch.nn.Linear` and its optimizer.

## 4. Run loop

- [ ] 4.1 Add `src/rl/train.py` with these parts:
  - the command line;
  - the train mode with epochs and task order, and the overlap for `vllm`;
  - the validation and `best/`;
  - the measure mode;
  - the memory check before step 1 and the recovery from an OOM in a step (design Decision 8);
  - the deadline and the safe stop with `status.json`;
  - the records of design Decision 12.

  Verify the parts without a model with tests: task order after a resume, the stop at the deadline, `status.json` after an error, the limit of OOM errors in a step.
- [ ] 4.2 Remove `src/rl_probe.py`. Check that no code in `src/` and `tests/` imports it. Verify that `uv run --no-project python -m pytest` passes.

## 5. Kaggle smoke tests

Local checks are only the short `pytest` tests. All checks with a model or with heavy work run on Kaggle. Each test runs on the train and the validation splits. Each test must take less than about 30 minutes. The job numbers are the next odd numbers. If a test fails, fix the code and run the same model again before the next model.

- [ ] 5.1 Add the job folder with `run.py` and the YAML configs. `run.py` clones the branch, installs `requirements-kaggle.txt`, removes torchao and makes the vLLM environment with a fixed version. Verify that the configs pass the config check locally.
- [ ] 5.2 Bielik 1.5B, engine `vllm`: 3 steps, a validation, a checkpoint at each step, the final adapter. Then a second job continues from the checkpoint for 2 steps. Verify `metrics.jsonl`, `status.json: complete` and the start step of job 2.
- [ ] 5.3 Bielik 1.5B: run the measure mode on 4 validation tasks. Run a short evaluation of the adapter of 5.2 with `model.adapters` on 4 validation tasks. Verify `metrics.json` of the evaluation and the group statistics.
- [ ] 5.4 Gemma 4 E2B, engine `transformers` on two GPUs: the same test as 5.2 without the second job. Verify that both copies have the same LoRA weights after a step.
- [ ] 5.5 Gemma 4 E4B, Bielik 4.5B and Qwen3.5-2B: the same test as 5.4 with their default engines. Verify the records and the peak GPU memory of each model. For Gemma 4 E4B, first run the memory check with `rl.max_sample_tokens: 8192`. Verify that the run stops before step 1 with the status `error`.
- [ ] 5.6 Qwen3.5-4B, engine `vllm`: 2 tasks, a group of 4, a context limit of 4096 tokens, 2 steps. Verify the records.
- [ ] 5.7 Acceptance: run 5.2 (with the second job), 5.4, 5.5 and 5.6 again on the final commit. The code is accepted only if all six models pass. Record each job in `jobs/JOBS.md`.

## 6. Documentation

- [ ] 6.1 Add to `docs/RL_METHODS.md` a short note: the method of idm-pro-047 stays, the trainer is our own code, and the reason (design Decision 1). Verify the note against the STE rules.
- [ ] 6.2 Add the entries to `docs/WORKLOG.md` and the job rows to `jobs/JOBS.md`. Write a comment in idm-pro-048 with the result of the acceptance. Add a note: the summary of the RL results comes after the real runs.
