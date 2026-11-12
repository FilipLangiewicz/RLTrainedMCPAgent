# RL methods

This file records the choice of the RL method and of the reward for E3 (issue idm-pro-047). The first part gives the decisions. The second part gives the options, the measurements and the reasons.

Status on 2026-11-12: draft. Some decisions wait for the SFT results.

## Decisions

### Made

1. RL starts after SFT. Before SFT, most groups of rollouts have only zero rewards, so RL gets almost no signal (see "Measurements").
2. After SFT, the RL probe (`src/rl_probe.py`) runs again on train or validation tasks. The team selects the models for RL from this second probe.
3. The test set is used only for the cost probe. No test task goes into the train set, the validation set or a choice of settings.
4. A Kaggle session stops after 12 h. Thus an RL run saves a checkpoint every 25 steps and continues in the next job. The checkpoint has the LoRA adapter, the optimizer state, the step and the state of the task filter.
5. The team can use more than one Kaggle account for RL. Each account needs access to the private model weights.

### Proposed, not confirmed

1. Method: GRPO with the DAPO and Dr. GRPO changes, in TRL (`GRPOTrainer`, `loss_type="dapo"`, no KL term), with LoRA (rank 16, all linear layers).
2. Reward: binary (1 for a correct task, 0 for all other results). A partial reward is a separate variant only.
3. No RFT round before GRPO. SFT already gives the warm start, and GPU time is the main limit.

### Open

1. The models for RL (after the second probe). The budget allows full RL for about 1 to 2 models.
2. The generation engine: `transformers` with batches, or vLLM. Jobs 51 and 53 measure vLLM on the T4.

## Options that we considered

| Option | Idea | Result of the review |
|---|---|---|
| PPO with a critic | Classic RLHF and RLVR. A second network of the same size predicts the value. | Rejected. The critic doubles the memory, and a T4 has 15 GB. |
| GRPO and its variants (DAPO, Dr. GRPO, GSPO, CISPO, RLOO) | The model samples a group of rollouts for one task. A rollout that is better than the group mean gets a positive advantage. No critic. | Proposed. It is the standard method in 2025-2026 (DeepSeek, Qwen, GLM-5, Magistral, Olmo 3). TRL has it with multi-turn tool calls. |
| GiGPO | GRPO plus an advantage for each step, from rollouts that reach the same state. | Later variant. Most of our tasks need 2 to 6 calls, so a trajectory-level advantage is enough at the start. |
| RFT (rejection-sampling fine-tuning) | Sample rollouts, keep the correct ones, then do SFT on them. | Not proposed. It learns only from successes, and it repeats most of the SFT effect. |
| On-policy distillation | The student samples, and a larger teacher with the same tokenizer scores each token. | Not proposed. It needs a strong teacher of the same family. Bielik has none. |
| Offline DPO or KTO | Pairs of a correct and an incorrect trajectory, without new samples. | Not proposed. Papers show clearly lower results than online RL. |
| Classic RLHF (reward model from human preferences) | A learned reward model scores the answers. | Not applicable. Our verifier is a program, so the reward is verifiable (RLVR). |

## Reward

The verifier (`src/verifier.py`) compares the final board with the expected board. It also returns the lists of absent and additional changes. Thus two forms of the reward are possible:

| Variant | Rule |
|---|---|
| A (main) | 1 for a correct task, else 0. A write on the board in a refusal task gives -0.2. A refusal in a task that needs an action gives 0. |
| B (separate run) | A, plus a partial reward for an incorrect change task: 0.2 x F0.5 of the changes. F0.5 gives more weight to precision, so additional changes cost reward. |

Reasons:

- The papers do not agree about partial rewards. A partial reward that grows with the number of actions is easy to exploit.
- In the probe, the partial reward added a signal to only 0 to 12.5% of the groups.
- A rollout that the loop rules or the 25-call limit stop gets 0 and no partial reward.

## Measurements

Jobs 41 to 49 ran the probe on the six base models (before SFT). Each model did up to 16 test tasks with 8 sampled rollouts for each task, at temperature 1.0. The details are in `jobs/JOBS.md`.

| Model | Time of one rollout | Sampled success | Groups with mixed rewards | Backward fits up to |
|---|---|---|---|---|
| Gemma 4 E2B | 9 s | 0.24 | 3 of 16 | 16384 tokens (PLE table in CPU memory) |
| Gemma 4 E4B | 20 s | 0.20 | 5 of 16 | about 5500 tokens (PLE table in CPU memory) |
| Bielik 1.5B | 15 s | 0.00 | 0 of 16 | 12288 tokens |
| Bielik 4.5B | 55 s | 0.01 | 1 of 10 | 8192 tokens |
| Qwen3.5-2B | 55 s | 0.01 | 1 of 10 | 12288 tokens |
| Qwen3.5-4B | 77 s | 0.14 | 3 of 8 | 8192 tokens |

Other results:

- In fp16 on a T4, the log-probabilities of the generation and of the forward pass differ by at most 0.037. No NaN occurred.
- Gemma 4 gives the same log-probabilities with and without the KV cache, and in train mode.
- For Gemma 4, the per-layer lookup table (PLE) can stay in CPU memory. The weights on the GPU then fall from 9.5 GB to 5.1 GB (E2B).
- A batch of 4 to 8 rollouts gives 2 to 3 times more tokens per second than one rollout, if it fits in memory.
- The Kaggle image has torchao 0.10. PEFT 0.21 stops with an ImportError for it, so a job must remove torchao first.

## Time estimate

The estimate is for 200 GRPO steps of 64 rollouts, a context of 5000 tokens and two T4 GPUs. Papers on small models with tools used 150 to 500 steps.

| Model | Hours |
|---|---|
| Bielik 1.5B | 27 |
| Gemma 4 E2B | 31 |
| Gemma 4 E4B | 65 |
| Qwen3.5-2B | 81 |
| Bielik 4.5B | 136 |
| Qwen3.5-4B | 207 |

The total for all six models is about 550 h. Until E3 the team has about 150 h of GPU time, also for SFT and the evaluations. The rollout times will change after SFT.

## Main sources

- DeepSeekMath (GRPO): https://arxiv.org/abs/2402.03300
- DAPO: https://arxiv.org/abs/2503.14476
- Dr. GRPO: https://arxiv.org/abs/2503.20783
- GiGPO: https://arxiv.org/abs/2505.10978
- LoRA Without Regret: https://thinkingmachines.ai/blog/lora/
- TRL GRPOTrainer: https://huggingface.co/docs/trl/en/grpo_trainer
