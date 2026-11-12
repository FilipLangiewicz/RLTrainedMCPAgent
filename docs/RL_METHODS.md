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
| Generation engine | `transformers` with batches for Gemma 4 E2B. vLLM is an option for the models with slow generation (Qwen3.5). | open | See "Generation engine". The final choice follows the selection of the models. |
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

## Generation engine

Jobs 51 and 53 measured vLLM 0.33 on one T4 in fp16. The prompt had about 4500 to 5200 tokens, and each rollout wrote 128 new tokens. Gemma 4 needs a patch on the T4: the attention kernel uses a tile of 16, because the T4 has only 64 KB of shared memory.

| Model | `transformers`, batch 1 / best batch | vLLM, 1 / 8 / 64 rollouts at the same time | vLLM start |
|---|---|---|---|
| Gemma 4 E2B | 11 / 39 tokens/s (batch 8) | 30 / 96 / 148 tokens/s | 5 min |
| Qwen3.5-2B | 16.5 / 52 tokens/s (batch 8) | 42 / 171 / 269 tokens/s | 11 min |

vLLM generates 2.5 to 5 times faster. The start of 5 to 11 minutes is about 1 to 2% of a job of 11 h, so it is not a problem.

The problem is the GPU memory. vLLM keeps most of the memory of its GPU. Thus vLLM generates on one GPU, and the trainer uses only the other GPU. With `transformers`, each GPU keeps its own copy of the model, and both GPUs generate and train. Estimate for one GRPO step (64 rollouts, context of 5000 tokens, backward times from the probe):

| Model | `transformers`, two copies | vLLM first, then the trainer | vLLM and the trainer at the same time |
|---|---|---|---|
| Gemma 4 E2B | about 9 min | about 14 min | about 12.5 min |
| Qwen3.5-2B | about 23 min | about 18.5 min | about 12 min |

For Gemma 4 E2B the backward pass takes most of the time, so vLLM gives no gain. For Qwen3.5 the generation takes most of the time, so vLLM gives 20 to 50%. If vLLM and the trainer work at the same time, the rollouts come from the weights of the previous step (off-policy). TRL corrects this with an importance weight.

Risks of vLLM: a separate environment (vLLM brings its own PyTorch), a patch for Gemma 4, and little free memory on the T4. In job 53 version 1, Qwen3.5-4B ran out of memory at the capture of the CUDA graphs. Version 2 measures Bielik 1.5B and Qwen3.5-4B with less memory.

## Main sources

- DeepSeekMath (GRPO): https://arxiv.org/abs/2402.03300
- DAPO: https://arxiv.org/abs/2503.14476
- Dr. GRPO: https://arxiv.org/abs/2503.20783
- GiGPO: https://arxiv.org/abs/2505.10978
- LoRA Without Regret: https://thinkingmachines.ai/blog/lora/
- TRL GRPOTrainer: https://huggingface.co/docs/trl/en/grpo_trainer
