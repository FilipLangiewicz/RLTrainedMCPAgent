# Candidate models

This file lists the models that the team selected for research. All models have a license that permits commercial use. The decision about SFT and RL for each model is open.

## Selection

| Model | Family | Size | Release | License | Hugging Face | Kaggle |
|---|---|---|---|---|---|---|
| `Qwen/Qwen3.5-2B` | Qwen3.5 | 2B | 2026-03-02 | Apache 2.0 | [link](https://huggingface.co/Qwen/Qwen3.5-2B) | no official `transformers` variation |
| `Qwen/Qwen3.5-4B` | Qwen3.5 | 4B (5B with the vision encoder) | 2026-03-02 | Apache 2.0 | [link](https://huggingface.co/Qwen/Qwen3.5-4B) | no official `transformers` variation |
| `speakleash/Bielik-1.5B-v3.0-Instruct` | Bielik v3 | 1.6B | 2025-05 | Apache 2.0 | [link](https://huggingface.co/speakleash/Bielik-1.5B-v3.0-Instruct) | none |
| `speakleash/Bielik-4.5B-v3.0-Instruct` | Bielik v3 | 4.6B | 2025-05 | Apache 2.0 | [link](https://huggingface.co/speakleash/Bielik-4.5B-v3.0-Instruct) | none |
| `google/gemma-4-E2B-it` | Gemma 4 | 2.3B effective (5.1B with embeddings) | 2026-04-02 | Apache 2.0 | [link](https://huggingface.co/google/gemma-4-E2B-it) | [gemma-4-e2b-it](https://www.kaggle.com/models/google/gemma-4/transformers/gemma-4-e2b-it) |
| `google/gemma-4-E4B-it` | Gemma 4 | 4.5B effective (8B with embeddings) | 2026-04-02 | Apache 2.0 | [link](https://huggingface.co/google/gemma-4-E4B-it) | [gemma-4-e4b-it](https://www.kaggle.com/models/google/gemma-4/transformers/gemma-4-e4b-it) |


## VRAM

The estimate is for local use with a Q4 quantization, a context of 32k tokens, and 0.7 GB for the runtime. The column "BF16 weights" gives the size of the weights for the training on Kaggle.

| Model | Q4 weights | KV cache, 32k | Total | Graphics card | BF16 weights |
|---|---|---|---|---|---|
| Qwen3.5-2B | 1.3 GB | 0.4 GB | 2.4 GB | 4 GB | 4 GB |
| Qwen3.5-4B | 2.6 GB | 1.0 GB | 4.3 GB | 6 GB | 8 GB |
| Bielik-1.5B | 1.0 GB | 0.27 GB (maximum context 8k) | 2.0 GB | 4 GB | 3.2 GB |
| Bielik-4.5B | 2.8 GB | 2.0 GB | 5.5 GB | 6 GB (small margin) | 9.2 GB |
| Gemma 4 E2B | 1.5 GB | 0.2 GB | 2.4 GB | 4 GB | 10.2 GB |
| Gemma 4 E4B | 2.8 GB | 0.5 GB | 4.0 GB | 6 GB | 16 GB |


## Comments

| Model | Comment |
|---|---|
| Qwen3.5-2B | Native tool calls. BFCL-V4 43.6, TAU2 48.8. The thinking mode can enter loops. |
| Qwen3.5-4B | Native tool calls. BFCL-V4 50.3, TAU2 79.9. The thinking mode is on by default. |
| Bielik-1.5B | Polish model. The model card does not mention tool calls. SFT must teach the format of the tool calls. The maximum context is 8192 tokens. |
| Bielik-4.5B | Polish model. The model card does not mention tool calls. It has the largest KV cache of the selection (60 layers with full attention). The maximum context is 32768 tokens. |
| Gemma 4 E2B | Native tool calls. Tau2 24.5. It also accepts images and audio. |
| Gemma 4 E4B | Native tool calls. Tau2 42.2. Official `transformers` and GGUF variations exist on Kaggle. |

The benchmark values come from the model cards. Each family uses a different benchmark setup. Thus compare the values only in one family.

## Config of a run

The config of a run is the file `jobs/runs/<folder>/<codename>.yaml`. `metrics.json` records the full config, the model data (`backend`, `family`, `path`, `revision`, `thinking`) and the version and the SHA-256 of the system prompt.

```yaml
model:
  backend: transformers   # transformers | openai | scripted
  family: qwen3.5         # qwen3.5 | gemma4 | bielik
  path: /kaggle/input/... # folder with the weights, or a Hugging Face id
  revision: <commit>      # recorded; used with a Hugging Face id
  thinking: false
  dtype: bfloat16
  max_new_tokens: 1024
agent:
  prompt: v3              # src/prompts/system-v3.md
  max_steps: 25
tasks:
  split: test
  limit: null
```

| Key | Default | Meaning |
|---|---|---|
| `model.backend` | (required) | `transformers` runs the weights. `openai` sends the messages to an OpenAI-compatible API. `scripted` gives fixed outputs for the tests. |
| `model.family` | (required, except for `openai`) | The chat format and the tool-call parser. |
| `model.path` | (required) | A folder loads with `local_files_only=True`, so a Kaggle job with attached weights needs no internet. For `openai`, the model name. |
| `model.revision` | none | The commit of the weights on Hugging Face. |
| `model.thinking` | `false` | The thinking mode. `bielik` has no thinking mode, so `true` stops the run. |
| `model.dtype`, `model.max_new_tokens`, `model.device` | `bfloat16`, `1024`, auto | Settings of `transformers`. |
| `model.base_url`, `model.api_key_env` | none, `OPENAI_API_KEY` | Settings of `openai`. The key comes only from the environment or `.env`. |
| `agent.prompt` | `v3` | The version of `src/prompts/system-<version>.md`. |
| `agent.max_steps` | `25` | The step limit of the agent loop. |

An unknown backend, an unknown family, thinking for `bielik` or a missing prompt file stops the run before the first task.

| Family | Tool-call format | Thinking |
|---|---|---|
| `qwen3.5` | `<tool_call><function=name><parameter=arg>value</parameter></function></tool_call>` (chat template) | `enable_thinking`; the text before `</think>` goes into the trajectory |
| `gemma4` | `<\|tool_call>call:name{arg:value}<tool_call\|>` (chat template) | `enable_thinking`; the text in `<\|channel>thought ... <channel\|>` goes into the trajectory |
| `bielik` | `<tool_call>{"name": ..., "arguments": {...}}</tool_call>`; `src/prompts/tools-bielik-v2.md` adds a compact list of the tools to the system prompt | none |
