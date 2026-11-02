# Candidate models

This file lists the models that the team selected for research. All models have a license that permits commercial use. The decision about SFT and RL for each model is open.

## Selection

| Model | Family | Size | Release | License | Hugging Face | Kaggle |
|---|---|---|---|---|---|---|
| `Qwen/Qwen3.5-2B` | Qwen3.5 | 2B | 2026-03-02 | Apache 2.0 | [link](https://huggingface.co/Qwen/Qwen3.5-2B) | no official `transformers` variation (1) |
| `Qwen/Qwen3.5-4B` | Qwen3.5 | 4B (5B with the vision encoder) | 2026-03-02 | Apache 2.0 | [link](https://huggingface.co/Qwen/Qwen3.5-4B) | no official `transformers` variation (1) |
| `speakleash/Bielik-1.5B-v3.0-Instruct` | Bielik v3 | 1.6B | 2025-05 (2) | Apache 2.0 | [link](https://huggingface.co/speakleash/Bielik-1.5B-v3.0-Instruct) | none |
| `speakleash/Bielik-4.5B-v3.0-Instruct` | Bielik v3 | 4.6B | 2025-05 (2) | Apache 2.0 | [link](https://huggingface.co/speakleash/Bielik-4.5B-v3.0-Instruct) | none |
| `google/gemma-4-E2B-it` | Gemma 4 | 2.3B effective (5.1B with embeddings) | 2026-04-02 | Apache 2.0 | [link](https://huggingface.co/google/gemma-4-E2B-it) | [gemma-4-e2b-it](https://www.kaggle.com/models/google/gemma-4/transformers/gemma-4-e2b-it) |
| `google/gemma-4-E4B-it` | Gemma 4 | 4.5B effective (8B with embeddings) | 2026-04-02 | Apache 2.0 | [link](https://huggingface.co/google/gemma-4-E4B-it) | [gemma-4-e4b-it](https://www.kaggle.com/models/google/gemma-4/transformers/gemma-4-e4b-it) |

1. The official Kaggle model [qwen-lm/qwen-3-5](https://www.kaggle.com/models/qwen-lm/qwen-3-5) has only the sizes 27B and larger. The Keras model [keras/qwen3-5](https://www.kaggle.com/models/keras/qwen3-5) has `qwen3_5_2b` and `qwen3_5_4b`, but only for Keras. A Kaggle job must download the model from Hugging Face.
2. The date of the technical report ([arXiv 2505.02550](https://arxiv.org/abs/2505.02550)). The Hugging Face repositories are gated. A Kaggle job needs a Hugging Face token with access to them.

## VRAM

The estimate is for local use with a Q4 quantization, a context of 32k tokens, and 0.7 GB for the runtime. The column "BF16 weights" gives the size of the weights for the training on Kaggle.

| Model | Q4 weights | KV cache, 32k | Total | Graphics card | BF16 weights |
|---|---|---|---|---|---|
| Qwen3.5-2B | 1.3 GB | 0.4 GB | 2.4 GB | 4 GB | 4 GB |
| Qwen3.5-4B | 2.6 GB | 1.0 GB | 4.3 GB | 6 GB | 8 GB |
| Bielik-1.5B | 1.0 GB | approx. 1 GB (3) | 2.7 GB | 4 GB | 3.2 GB |
| Bielik-4.5B | 2.8 GB | approx. 2 GB (3) | 5.5 GB | 6 GB (small margin) | 9.2 GB |
| Gemma 4 E2B | 1.5 GB (4) | 0.2 GB | 2.4 GB | 4 GB | 10.2 GB |
| Gemma 4 E4B | 2.8 GB (4) | 0.5 GB | 4.0 GB | 6 GB | 16 GB |

3. The `config.json` files of Bielik are gated. The estimate uses the Qwen2.5 architecture with full attention in all layers.
4. Gemma 4 can keep the per-layer embeddings in the CPU memory. The value is for the effective parameters only.

The KV cache of Qwen3.5 and Gemma 4 is small for these reasons:

- Qwen3.5 uses full attention only in one of four layers. The other layers use linear attention (Gated DeltaNet) with a state of fixed size.
- Gemma 4 uses a sliding window of 512 tokens in most layers. Many layers share one KV cache.

## Comments

| Model | Comment |
|---|---|
| Qwen3.5-2B | Native tool calls. BFCL-V4 43.6, TAU2 48.8. The thinking mode can enter loops. |
| Qwen3.5-4B | Native tool calls. BFCL-V4 50.3, TAU2 79.9. The thinking mode is on by default. |
| Bielik-1.5B | Polish model. The model card does not mention tool calls. SFT must teach the format of the tool calls. |
| Bielik-4.5B | Polish model. The model card does not mention tool calls. It has the largest KV cache of the selection. |
| Gemma 4 E2B | Native tool calls. Tau2 24.5. It also accepts images and audio. |
| Gemma 4 E4B | Native tool calls. Tau2 42.2. Official `transformers` and GGUF variations exist on Kaggle. |

The benchmark values come from the model cards. Each family uses a different benchmark setup. Thus compare the values only in one family.

## Changes to the code

- Qwen3.5 uses a tool call format that is different from Qwen3 (the parser `qwen3_coder`). The parser in `src/agent.py` must change.
- Gemma 4 uses its own chat template and tool call format.
- Qwen3.5 and Gemma 4 need a new version of `transformers`. This change requires a new lock.
