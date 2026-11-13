# RL methods

This file records the choice of the RL method and of the reward for E3 (issue idm-pro-047). The first part gives the decisions. The second part gives the options, the measurements and the reasons.

Status on 2026-11-12: draft. Some decisions wait for the SFT results.

## Decisions

| Topic | Decision | Status | Reason |
|---|---|---|---|
| Method | GRPO with the DAPO and Dr. GRPO changes, in TRL (`GRPOTrainer`, `loss_type="dapo"`, no KL term) | proposed | Standard method in 2025-2026. No critic, so it fits on a T4. TRL supports multi-turn tool calls. |
| Weights | LoRA, rank 16, all linear layers | proposed | In RL, LoRA gives the same result as full fine-tuning. The memory is small. |
| Reward | Binary: 1 for a correct task, else 0. A write on the board in a refusal task gives -0.2. | proposed | A binary reward is difficult to exploit. A partial reward helped only 0 to 12.5% of the groups. |
| Partial reward | Only as a separate variant (one change) | proposed | The evidence in papers is mixed. |
| Start of RL | After SFT | made | Before SFT, most groups of rollouts have only zero rewards. |
| Warm start with RFT | No RFT round before GRPO | proposed | SFT already gives the warm start. GPU time is the main limit. |
| Models for RL | Selected after a second probe on the SFT models, on train or validation tasks | made (selection open) | The budget allows full RL for about 1 to 2 models. Rollout times change after SFT. |
| Generation engine | Bielik 1.5B and Qwen3.5-2B: vLLM on GPU 0, the trainer on GPU 1. Gemma 4: `transformers` on both GPUs. | proposed | Measured in jobs 51 to 61. See "Generation engine and GPU layout". |
| Long runs | A checkpoint every 25 steps (LoRA adapter, optimizer state, step, task filter). The next job continues from it. | made | A Kaggle session stops after 12 h. |
| Kaggle accounts | More than one account is allowed for RL | made | It shortens the calendar time. Each account needs access to the private weights. |
| Test set | Used only for the cost probe | made | No test task goes into the train set, the validation set or a choice of settings. |

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

## Generation engine and GPU layout

Jobs 51 to 61 measured vLLM 0.33 on the T4 in fp16, with real agent rollouts (our parser, the simulator, 64 rollouts at the same time). Gemma 4 needs a patch on the T4: the attention kernel uses a tile of 16, because the T4 has only 64 KB of shared memory.

### Generation of 64 rollouts

| Model | `transformers`, one rollout after the other, one GPU | vLLM, 64 at the same time | vLLM start |
|---|---|---|---|
| Gemma 4 E2B | 9.6 min | 2.1 min | 5.6 min |
| Gemma 4 E4B | 21 min | 1.4 min (two GPUs) | 6.4 min |
| Bielik 1.5B | 16 min | 2.1 min | 2.8 min |
| Bielik 4.5B | 59 min | 8.2 min | 2.5 min |
| Qwen3.5-2B | 58 min | 6.2 min | 11.3 min |
| Qwen3.5-4B | 82 min | 44 min | 11.7 min |

- The success rates with vLLM are the same as with `transformers`. Thus vLLM does not change the behavior of the agent.
- vLLM and `transformers` give the same log-probabilities: the mean difference is 0.0008 to 0.0027, and 99% of the tokens are below 0.036. This is also true with a LoRA adapter.
- Qwen3.5-4B is slow in vLLM: after 8.6 GB of weights, the KV cache holds only about 15 rollouts at the same time.

### One RL step (64 rollouts, two T4 GPUs)

Layout A: each GPU keeps a copy of the model in `transformers`, generates one half of the rollouts and trains on it. Layout B: vLLM with the LoRA adapter generates on GPU 0, and at the same time the trainer works on GPU 1. After each step, the trainer saves the adapter, and vLLM loads it without a restart. The save and the load take less than 1 s.

| Model | Faster layout | One step | 200 steps | Source |
|---|---|---|---|---|
| Bielik 1.5B | B | 5.8 min | about 19 h | measured (job 59) |
| Gemma 4 E2B | A | 11.6 min | about 39 h | calculated from measured parts. B measured 13.8 min. |
| Gemma 4 E4B | A | about 20 min | about 67 h | calculated from measured parts |
| Qwen3.5-2B | B | 28 min | about 95 h | measured (job 59) |
| Bielik 4.5B | B | about 16 min | about 53 h | estimate: the measured generation and the backward times of the probe |
| Qwen3.5-4B | B | about 64 min | about 210 h | estimate. The backward pass of trajectories with 8000 tokens is near the memory limit. |

In all layouts the backward pass takes most of the time. The trajectories of Qwen3.5-2B have about 8000 tokens, almost two times more than the trajectories of Bielik and Gemma. Thus a limit of the context (shorter tool results or a window of the last turns) is the strongest way to make RL faster.

Layout C (vLLM generates, then sleeps, and two trainer copies use both GPUs) failed three times in job 61. The causes were full RAM, GPU memory that the sleeping vLLM keeps, and an illegal memory access. The team does not use this layout.

### Requirements for the RL code (issue idm-pro-048)

- Compute the log-probabilities in chunks. The vocabulary of Qwen has 248k tokens. Thus 2800 trained tokens need about 2.8 GB for the logits alone.
- Limit the length of a trajectory. Some Qwen3.5-2B trajectories had 25000 tokens and did not fit in the backward pass.
- Remove torchao in each Kaggle job that uses PEFT.
- Keep vLLM in a separate environment (it brings its own PyTorch). Use `--max-num-batched-tokens 4096` and 85 to 90% of the GPU memory for models with about 9 GB of weights.
- Keep the PLE table of Gemma 4 in CPU memory in the trainer.

## Main sources

- DeepSeekMath (GRPO): https://arxiv.org/abs/2402.03300
- DAPO: https://arxiv.org/abs/2503.14476
- Dr. GRPO: https://arxiv.org/abs/2503.20783
- GiGPO: https://arxiv.org/abs/2505.10978
- LoRA Without Regret: https://thinkingmachines.ai/blog/lora/
- TRL GRPOTrainer: https://huggingface.co/docs/trl/en/grpo_trainer
