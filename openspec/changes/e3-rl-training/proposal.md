# Proposal

## Why

E3 needs a model that learns from a reward after SFT (issue idm-pro-048). Issue idm-pro-047 selected the method, the reward and the GPU layouts. The repository has only a probe that measures the cost of RL (`src/rl_probe.py`). It does not train a model. The RL code must be ready and tested on Kaggle before the SFT models are ready.

## What Changes

- Add the package `src/rl/`. It trains a LoRA adapter with GRPO on the train tasks of the simulator. The method is the method of idm-pro-047:
  - the DAPO loss (token-level loss, clip-higher, no KL term) and the Dr. GRPO advantage (no division by the standard deviation);
  - a binary reward, with the partial reward as a variant;
  - groups with equal rewards do not go to the backward pass.
- The code works for each model of the families `qwen3.5`, `gemma4` and `bielik`. The model, the start weights (base or SFT) and all settings come from a YAML config. The defaults are the decisions of idm-pro-047.
- Two generation engines: vLLM on GPU 0 and the trainer on GPU 1, or `transformers` with one model copy on each GPU. The config selects the engine.
- The trainer uses the exact tokens that the model sampled in each turn, with their log-probabilities. The agent loop and the evaluation do not change.
- A run saves a checkpoint every N steps and stops before the 12-hour limit of Kaggle. The next job continues from the checkpoint.
- A "measure" mode samples groups of rollouts and gives the statistics of the reward without a model update. The second probe after SFT uses this mode.
- Rollouts of an RL run can have tighter limits than the evaluation (a context limit, the loop limits). The evaluation on the test set keeps its limits.
- The `transformers` backend of the model layer loads LoRA adapters and merges them into the base weights. Thus the evaluation can run a model after SFT and after RL.
- **BREAKING**: remove `src/rl_probe.py`. The new code replaces it. Old jobs that import it do not run again.

Out of scope:

- The real RL runs, the choice of the models for RL and the RL settings (idm-pro-049 to idm-pro-056). `jobs/JOBS.md` and `docs/WORKLOG.md` record this research work.
- The SFT code (idm-pro-037).
- The partial reward as a tested variant. The code supports it, but no run uses it in this change.
- GiGPO, RFT, the asynchronous trainer of TRL 1.18 and other methods that idm-pro-047 did not select.
- A document with the results of RL in `docs/`. It comes after the RL runs.

## Capabilities

### New Capabilities

- `rl-training`: the GRPO update of a LoRA adapter on the simulator tasks, and the reward. It also covers the generation engines, the checkpoints, the measure mode and the records of a run.

### Modified Capabilities

- `model-layer`: the `transformers` backend loads LoRA adapters and merges them into the base weights.

## Impact

- New code: `src/rl/` (see `design.md` for the files).
- Changed code: `src/models.py` (adapters in the `transformers` backend).
- Removed code: `src/rl_probe.py`.
- New tests in `tests/` for the parts that do not need a model.
- Kaggle jobs in `jobs/runs/`: smoke tests of all six models on GPU. vLLM stays in a separate environment in each job.
- The lock does not change. TRL stays in the lock, but the RL code does not use it.
- `docs/RL_METHODS.md` gets one note: the method stays, and the trainer is our own code (see `design.md`).
