"""Probe of the cost and the signal of RL for one model (issue idm-pro-047).

The probe only measures. It does not train the model. It writes small files:
- `probe.json`: the summary of all parts.
- `rollouts.jsonl`: one line for each sampled rollout, without the task id and without the messages.

Parts:
1. generation: the speed of sampled generation for batch sizes 1, 4 and 8, and the difference of the
   log-probabilities between the generation and the forward pass of the trainer.
2. rollouts: a group of sampled rollouts for each task, with the binary reward and a partial reward.
3. backward: the time and the GPU memory of one LoRA forward and backward pass. The probe uses real
   trajectories and longer sequences.

Usage: python -m src.rl_probe <config.yaml> --output <folder>
"""

import argparse
import asyncio
import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

import mcp
import yaml

from src.agent import run_task, tool_schema
from src.environment import diff, load_board
from src.models import load_prompt, make_model
from src.tasks import CATEGORIES, CHANGE_CATEGORIES, board_path, load_tasks
from src.tools import build_server
from src.verifier import grade, match_changes

DEFAULTS = {"split": "test", "tasks": 16, "group": 8, "rollout_minutes": 60, "batch_sizes": [1, 4, 8],
            "new_tokens": 128, "lora_rank": 16, "lengths": [2048, 4096, 8192, 12288], "seed": 0}


def gpu_gb(torch) -> float:
    return round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else 0.0


def reset_peak(torch) -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def sync(torch) -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


async def _list_tools(server) -> list[dict]:
    async with mcp.Client(server) as client:
        return [tool_schema(t) for t in (await client.list_tools()).tools]


def render(model, messages: list[dict], tools: list[dict], generation_prompt: bool) -> str:
    family = model.family
    messages, tools = family.prepare(family._with_mapping_arguments(messages), tools)
    return model.tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=generation_prompt,
                                               tokenize=False, **family.template_args(model.thinking))


def token_count(model, text: str) -> int:
    return len(model.tokenizer(text, add_special_tokens=False)["input_ids"])


# Part 1: generation

def probe_generation(model, prompt_text: str, cfg: dict) -> dict:
    torch, tok = model.torch, model.tokenizer
    inputs = tok(prompt_text, return_tensors="pt", add_special_tokens=False).to(model.device)
    n_prompt, n_new = inputs["input_ids"].shape[1], cfg["new_tokens"]
    sampling = {"do_sample": True, "temperature": 1.0, "top_p": 1.0, "top_k": 0, "max_new_tokens": n_new, "min_new_tokens": n_new}
    # The first call of generate is slow (kernel compile and cache setup), so it does not count.
    with torch.no_grad():
        model.model.generate(**inputs, **{**sampling, "max_new_tokens": 4, "min_new_tokens": 4})
    rows = []
    for batch in cfg["batch_sizes"]:
        reset_peak(torch)
        start = time.perf_counter()
        try:
            with torch.no_grad():
                model.model.generate(**inputs, num_return_sequences=batch, **sampling)
            sync(torch)
            seconds = time.perf_counter() - start
            rows.append({"batch": batch, "prompt_tokens": n_prompt, "new_tokens": n_new, "time_s": round(seconds, 2),
                         "tokens_per_s": round(batch * n_new / seconds, 1), "peak_gb": gpu_gb(torch)})
        except torch.cuda.OutOfMemoryError:
            rows.append({"batch": batch, "prompt_tokens": n_prompt, "error": "out of memory"})
        print("generation", rows[-1], flush=True)

    # The trainer computes the log-probabilities again with a full forward pass. A difference to the values
    # of the generation makes the policy ratio of RL wrong, also before the first update.
    with torch.no_grad():
        out = model.model.generate(**inputs, return_dict_in_generate=True, output_logits=True, **sampling)
        new_ids = out.sequences[0, n_prompt:]
        gen_lp = torch.stack([torch.log_softmax(l[0].float(), -1)[t] for l, t in zip(out.logits, new_ids)])
        logits = model.model(input_ids=out.sequences, logits_to_keep=n_new + 1).logits[0, :-1].float()
        fwd_lp = torch.log_softmax(logits, -1).gather(-1, new_ids[:, None])[:, 0]
        delta = (gen_lp - fwd_lp).abs()
        ratio = torch.exp(fwd_lp - gen_lp)
    mismatch = {"tokens": int(n_new), "mean_abs_logprob_diff": round(delta.mean().item(), 5),
                "max_abs_logprob_diff": round(delta.max().item(), 5),
                "ratio_min": round(ratio.min().item(), 4), "ratio_max": round(ratio.max().item(), 4)}
    print("mismatch", mismatch, flush=True)
    return {"batches": rows, "mismatch": mismatch}


# Part 2: rollouts

def select_tasks(split: str, count: int, seed: int) -> list:
    """Take the tasks round robin over the categories, so that a short run still covers all categories."""
    tasks = load_tasks(split)
    rng = random.Random(seed)
    groups = {c: [t for t in tasks if t.category == c] for c in CATEGORIES}
    for group in groups.values():
        rng.shuffle(group)
    order = [groups[c][i] for i in range(max(map(len, groups.values()))) for c in CATEGORIES if i < len(groups[c])]
    return order[:count]


def partial_reward(task, initial, final, binary: float) -> float:
    """The share of correct changes: matched / (expected + additional). Other categories keep the binary reward."""
    if task.category not in CHANGE_CATEGORIES:
        return binary
    missing, additional = match_changes(task.changes, diff(initial, final))
    matched = len(task.changes) - len(missing)
    return round(matched / (len(task.changes) + len(additional)), 4)


def rollout(model, task, prompt, agent: dict) -> tuple[dict, list[dict]]:
    initial = load_board(board_path(task.board))
    board = initial.copy_board()
    traj = run_task(model, build_server(board), task.instruction, prompt, agent["max_steps"], task.id,
                    agent["loop_limit"], agent["error_limit"])
    if traj.stop_reason == "error":
        model.free_memory()
        binary, partial = 0.0, 0.0
    else:
        g = grade(task, initial, board, traj.final_answer)
        binary = 1.0 if g.grade in ("correct", "correct_refusal") else 0.0
        partial = partial_reward(task, initial, board, binary)
    row = {"category": task.category, "difficulty": task.difficulty, "reward": binary, "partial_reward": partial,
           "stop_reason": traj.stop_reason, "steps": traj.steps, "tool_calls": len(traj.tool_calls),
           "invalid_calls": traj.invalid_calls, "input_tokens": traj.input_tokens,
           "output_tokens": traj.output_tokens, "time_s": traj.time_s}
    return row, traj.messages


def summarize_groups(rows: list[dict]) -> dict:
    groups: dict[int, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["task_index"], []).append(r)
    full = [g for g in groups.values() if len(g) == max(len(x) for x in groups.values())]

    def spread(g, key):
        return len({r[key] for r in g}) > 1

    n = len(full) or 1
    per_category = {}
    for c in CATEGORIES:
        rows_c = [r for r in rows if r["category"] == c]
        if rows_c:
            per_category[c] = round(sum(r["reward"] for r in rows_c) / len(rows_c), 3)
    times = sorted(r["time_s"] for r in rows)
    return {
        "tasks": len(groups), "complete_groups": len(full), "rollouts": len(rows),
        "sampled_pass1": round(sum(r["reward"] for r in rows) / max(len(rows), 1), 3),
        "pass_at_group": round(sum(any(r["reward"] for r in g) for g in full) / n, 3),
        "groups_with_signal": round(sum(spread(g, "reward") for g in full) / n, 3),
        "groups_all_zero": round(sum(all(r["reward"] == 0 for r in g) for g in full) / n, 3),
        "groups_all_one": round(sum(all(r["reward"] == 1 for r in g) for g in full) / n, 3),
        "groups_with_partial_signal_only": round(
            sum(spread(g, "partial_reward") and not spread(g, "reward") for g in full) / n, 3),
        "reward_by_category": per_category,
        "rollout_time_s": {"mean": round(sum(times) / max(len(times), 1), 1),
                           "median": times[len(times) // 2] if times else None, "max": times[-1] if times else None},
        "output_tokens_mean": round(sum(r["output_tokens"] for r in rows) / max(len(rows), 1), 1),
        "input_tokens_mean": round(sum(r["input_tokens"] for r in rows) / max(len(rows), 1), 1),
        "stop_reasons": {s: sum(r["stop_reason"] == s for r in rows) for s in sorted({r["stop_reason"] for r in rows})},
    }


# Part 3: backward

def assistant_positions(model, messages: list[dict], tools: list[dict]) -> tuple[list[int], list[int]]:
    """The token ids of the full conversation and the positions of the tokens that the model wrote."""
    ids = model.tokenizer(render(model, messages, tools, False), add_special_tokens=False)["input_ids"]
    positions = []
    for i, m in enumerate(messages):
        if m["role"] != "assistant":
            continue
        start = token_count(model, render(model, messages[:i], tools, True))
        end = token_count(model, render(model, messages[: i + 1], tools, False))
        positions.extend(range(start, min(end, len(ids))))
    return ids, positions


def lora_model(model, rank: int):
    from peft import LoraConfig, get_peft_model

    model.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.model.enable_input_require_grads()
    config = LoraConfig(r=rank, lora_alpha=2 * rank, lora_dropout=0.0, target_modules="all-linear",
                        exclude_modules=r".*(vision|audio|visual).*", task_type="CAUSAL_LM")
    peft = get_peft_model(model.model, config)
    peft.train()
    trainable = sum(p.numel() for p in peft.parameters() if p.requires_grad)
    total = sum(p.numel() for p in peft.parameters())
    return peft, {"lora_rank": rank, "trainable_params": trainable, "all_params": total,
                  "trainable_share": round(trainable / total, 5)}


def backward_once(model, peft, ids: list[int], positions: list[int]) -> dict:
    """One forward and backward pass of a policy-gradient loss with the advantage 1 on the given tokens."""
    torch = model.torch
    reset_peak(torch)
    start = time.perf_counter()
    try:
        input_ids = torch.tensor([ids], device=model.device)
        # The logits at position p - 1 give the probability of the token at position p.
        keep = torch.tensor([p - 1 for p in positions], device=model.device)
        with torch.autocast("cuda", dtype=torch.float16, enabled=torch.cuda.is_available()):
            logits = peft(input_ids=input_ids, logits_to_keep=keep).logits[0].float()
        logp = torch.log_softmax(logits, -1).gather(-1, input_ids[0, keep + 1][:, None])[:, 0]
        loss = -logp.mean()
        loss.backward()
        sync(torch)
        grads = [p.grad for p in peft.parameters() if p.grad is not None]
        norm = torch.sqrt(sum((g.float() ** 2).sum() for g in grads)).item() if grads else 0.0
        row = {"tokens": len(ids), "trained_tokens": len(positions), "time_s": round(time.perf_counter() - start, 2),
               "peak_gb": gpu_gb(torch), "loss": round(loss.item(), 4), "grad_norm": round(norm, 4),
               "finite": bool(torch.isfinite(loss).item() and math.isfinite(norm))}
    except torch.cuda.OutOfMemoryError:
        row = {"tokens": len(ids), "trained_tokens": len(positions), "error": "out of memory"}
    peft.zero_grad(set_to_none=True)
    reset_peak(torch)
    print("backward", row, flush=True)
    return row


def offload_embeddings(model, device: str = "cuda") -> dict:
    """Keep the per-layer lookup tables (PLE) of Gemma 4 in CPU memory and put all other weights on the GPU.

    A lookup in such a table needs no matrix product. Thus the CPU gives the rows for the tokens of a sequence quickly.
    """
    torch = model.torch
    sizes = sorted(((sum(p.numel() for p in m.parameters(recurse=False)), n) for n, m in model.model.named_modules()), reverse=True)
    print("largest modules", sizes[:6], flush=True)
    tables = [(n, m) for n, m in model.model.named_modules() if isinstance(m, torch.nn.Embedding) and "per_layer" in n]
    # Move each tensor on its own: a move of the full model first does not fit on the GPU for Gemma 4 E4B.
    keep = {id(t) for _, m in tables for t in [*m.parameters(), *m.buffers()]}
    model.keep_on_cpu = keep
    move_weights(model, device)
    for _, m in tables:
        m.register_forward_pre_hook(lambda mod, args: tuple(a.to("cpu") if torch.is_tensor(a) else a for a in args))
        m.register_forward_hook(lambda mod, args, out: out.to(model.device))
    return {"tables": [n for n, _ in tables], "cpu_params": sum(m.weight.numel() for _, m in tables)}


def move_weights(model, device: str) -> None:
    """Move all weights except the PLE tables. LoRA weights and their gradients move with them."""
    keep = getattr(model, "keep_on_cpu", set())
    for t in [*model.model.parameters(), *model.model.buffers()]:
        if id(t) not in keep:
            t.data = t.data.to(device)
            if getattr(t, "grad", None) is not None:
                t.grad = t.grad.to(device)
    model.device = device
    if model.torch.cuda.is_available():
        model.torch.cuda.empty_cache()


def probe_cache(model, prompt_text: str, tokens: int = 128) -> tuple[dict, tuple]:
    """Compare the log-probabilities with and without the KV cache in one forward pass.

    Gemma 4 shares the KV state over layers. Reports say that some code paths give wrong logits with use_cache=False.
    The trainer uses use_cache=False, so a difference here makes RL wrong.
    """
    torch = model.torch
    ids = model.tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)["input_ids"].to(model.device)
    with torch.no_grad():
        a = torch.log_softmax(model.model(input_ids=ids, use_cache=True, logits_to_keep=tokens).logits[0].float(), -1)
        b = torch.log_softmax(model.model(input_ids=ids, use_cache=False, logits_to_keep=tokens).logits[0].float(), -1)
    top = a.argmax(-1)
    row = {"tokens": tokens, "max_abs_logprob_diff": round((a - b).abs().max().item(), 5),
           "top1_logprob_diff": round((a.gather(-1, top[:, None]) - b.gather(-1, top[:, None])).abs().max().item(), 5),
           "same_argmax": round((a.argmax(-1) == b.argmax(-1)).float().mean().item(), 4)}
    print("cache", row, flush=True)
    return row, (ids, a)


def train_mode_check(model, peft, ref: tuple) -> dict:
    """Compare the log-probabilities of the LoRA model in train mode with the reference. Train mode recomputes activations and uses no cache."""
    torch = model.torch
    ids, a = ref
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16, enabled=torch.cuda.is_available()):
        c = torch.log_softmax(peft(input_ids=ids, logits_to_keep=a.shape[0]).logits[0].float(), -1)
    top = a.argmax(-1)
    row = {"top1_logprob_diff": round((a.gather(-1, top[:, None]) - c.gather(-1, top[:, None])).abs().max().item(), 5),
           "same_argmax": round((a.argmax(-1) == c.argmax(-1)).float().mean().item(), 4)}
    print("train mode", row, flush=True)
    return row


def probe_backward(model, conversations: list[list[dict]], tools: list[dict], cfg: dict, ref: tuple | None = None) -> dict:
    peft, info = lora_model(model, cfg["lora_rank"])
    print("lora", info, flush=True)
    if ref is not None:
        info["train_mode_check"] = train_mode_check(model, peft, ref)
    built = sorted((assistant_positions(model, m, tools) for m in conversations), key=lambda x: len(x[0]))
    built = [b for b in built if b[1]]
    real = []
    if built:
        for ids, positions in {id(b): b for b in (built[0], built[len(built) // 2], built[-1])}.values():
            real.append(backward_once(model, peft, ids, positions))
    ladder = []
    if built:
        # Longer sequences from a real trajectory: the trajectory repeats, and the last 300 tokens count for the loss.
        base = built[-1][0]
        for length in cfg["lengths"]:
            ids = (base * (length // len(base) + 1))[:length]
            row = backward_once(model, peft, ids, list(range(length - 300, length)))
            ladder.append(row)
            if "error" in row:
                break
    return {**info, "real": real, "ladder": ladder}


# vLLM: real agent rollouts through a local server

PATCH_LINES = [
    "import importlib.util, pathlib",
    "root = pathlib.Path(importlib.util.find_spec('vllm').origin).parent",
    "wrapper = '\\n'.join(['', 'def _get_tile_size(*args, **kwargs):',",
    "    '    import os as _os', '    import torch as _torch', '    size = _get_tile_size_orig(*args, **kwargs)',",
    "    '    if _os.environ.get(\"VLLM_TURING_TILE\") == \"1\" and _torch.cuda.get_device_capability()[0] < 8:',",
    "    '        return min(size, 16)', '    return size', ''])",
    "for path in root.rglob('*.py'):",
    "    text = path.read_text(errors='ignore')",
    "    if 'def _get_tile_size(' in text and '_get_tile_size_orig' not in text:",
    "        path.write_text(text.replace('def _get_tile_size(', 'def _get_tile_size_orig(') + wrapper)",
    "        print('patched', path)",
]
# The code runs in the vLLM environment. It wraps _get_tile_size: a tile of 16 fits the 64 KB of shared memory of a T4.
PATCH_CODE = "\n".join(PATCH_LINES)


class VllmServerModel:
    """A model behind a local vLLM server. The prompt and the parser are the same as in LocalModel.

    The class sends the token ids of the prompt, so that the server does not add a second BOS token.
    """

    backend = "vllm"

    def __init__(self, family: str, path: str, url: str, temperature: float, max_new_tokens: int, keep: int, max_len: int):
        import threading

        import transformers
        from openai import OpenAI

        from src.models import get_family

        self.family, self.path, self.thinking, self.steps = get_family(family), path, False, 0
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.client = OpenAI(base_url=url + "/v1", api_key="none", max_retries=2, timeout=900)
        self.temperature, self.max_new_tokens, self.keep, self.max_len = temperature, max_new_tokens, keep, max_len
        self.top_k = 0
        self.served = "m"  # The name of the base model or of the active LoRA adapter on the server.
        self.samples, self.lock = [], threading.Lock()
        self.special = {t for t in (self.tokenizer.eos_token, self.tokenizer.pad_token, self.tokenizer.bos_token) if t}

    def free_memory(self) -> None:
        return None

    def _complete(self, ids: list[int], room: int, want: bool):
        extra = {"top_k": self.top_k, "skip_special_tokens": False, "return_tokens_as_token_ids": True}
        return self.client.completions.create(model=self.served, prompt=ids, max_tokens=room, temperature=self.temperature,
                                              top_p=1.0, logprobs=1 if want else None, extra_body=extra)

    def generate(self, messages, tools):
        from src.models import ModelOutput

        self.steps += 1
        prompt = self.family.render(self.tokenizer, messages, tools, self.thinking)
        ids = self.tokenizer(prompt, add_special_tokens=False)["input_ids"]
        with self.lock:
            want = len(self.samples) < self.keep
        room = min(self.max_new_tokens, self.max_len - len(ids))
        if room < 16:
            raise RuntimeError(f"context full: {len(ids)} prompt tokens, limit {self.max_len}")
        try:
            response = self._complete(ids, room, want)
        except Exception as e:  # Some vLLM versions accept only -1 to disable top-k.
            if "top_k" not in str(e) or self.top_k == -1:
                raise
            self.top_k = -1
            response = self._complete(ids, room, want)
        choice = response.choices[0]
        text = choice.text
        for token in self.special:
            text = text.replace(token, "")
        if want and choice.logprobs and choice.logprobs.tokens:
            tokens = [int(t.split(":")[-1]) for t in choice.logprobs.tokens]
            with self.lock:
                self.samples.append({"prompt": ids, "tokens": tokens, "logprobs": choice.logprobs.token_logprobs})
        content, calls, thinking = self.family.parse(self.family.clean(text), tools, self.steps)
        return ModelOutput(text=content, calls=calls, thinking_text=thinking,
                           input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens)


def start_server(model_cfg: dict, vcfg: dict) -> tuple:
    """Start `vllm serve` from the separate environment. Return the process, the URL, the start time in seconds and the context limit."""
    import os
    import subprocess
    import urllib.request

    python = os.environ["VLLM_PYTHON"]
    if vcfg.get("patch"):
        subprocess.run([python, "-c", PATCH_CODE], check=True)
    config = json.loads((Path(model_cfg["path"]) / "config.json").read_text())
    limit = config.get("text_config", config).get("max_position_embeddings") or vcfg["max_len"]
    port = vcfg.get("port", 8000)
    cmd = [python, "-m", "vllm.entrypoints.openai.api_server", "--model", model_cfg["path"], "--served-model-name", "m",
           "--dtype", "float16", "--max-model-len", str(min(vcfg["max_len"], limit)), "--port", str(port),
           "--gpu-memory-utilization", str(vcfg.get("mem", 0.8)), "--enable-prefix-caching",
           "--max-num-seqs", str(vcfg.get("max_seqs", 64)), "--tensor-parallel-size", str(vcfg.get("tp", 1)),
           "--compilation-config", json.dumps({"cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32, 64]})]
    if vcfg.get("batched_tokens"):
        # A smaller prefill chunk needs less activation memory. Then the KV cache of a 4B model fits on a T4.
        cmd += ["--max-num-batched-tokens", str(vcfg["batched_tokens"])]
    env = {**os.environ, "VLLM_TURING_TILE": "1" if vcfg.get("patch") else "0"}
    if vcfg.get("gpus") is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(vcfg["gpus"])
    if vcfg.get("lora_rank"):
        # The server keeps the base weights and gets each new LoRA adapter at run time, without a restart.
        env["VLLM_ALLOW_RUNTIME_LORA_UPDATING"] = "True"
        cmd += ["--enable-lora", "--max-lora-rank", str(vcfg["lora_rank"]), "--max-loras", "2"]
    if vcfg.get("sleep"):
        # Sleep mode frees the GPU between the generation and the training. The endpoints need the dev mode.
        env["VLLM_SERVER_DEV_MODE"] = "1"
        cmd += ["--enable-sleep-mode"]
    start = time.perf_counter()
    # A new session gives the server and its engine processes one process group, so that one signal stops them all.
    proc = subprocess.Popen(cmd, env=env, start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    while time.perf_counter() - start < 60 * vcfg.get("start_minutes", 30):
        if proc.poll() is not None:
            raise RuntimeError(f"vllm serve stopped with code {proc.returncode}")
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                if r.status == 200:
                    return proc, url, round(time.perf_counter() - start, 1), min(vcfg["max_len"], limit)
        except OSError:
            pass
        time.sleep(5)
    stop_server(proc)
    raise TimeoutError("vllm serve did not start in time")


def stop_server(proc) -> None:
    import os
    import signal
    import subprocess

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
            proc.wait(timeout=90)
            break
        except ProcessLookupError:
            break
        except subprocess.TimeoutExpired:
            continue
    time.sleep(10)


def check_logprobs(model_cfg: dict, probe: dict, samples: list[dict]) -> dict:
    """Compute the log-probabilities of the vLLM samples again in transformers, as the trainer does."""
    torch_model = make_model({**model_cfg, "backend": "transformers", "temperature": 0.0})
    if probe.get("offload_ple"):
        offload_embeddings(torch_model)
    torch = torch_model.torch
    diffs = []
    for s in samples:
        ids = torch.tensor([s["prompt"] + s["tokens"]], device=torch_model.device)
        with torch.no_grad():
            logits = torch_model.model(input_ids=ids, logits_to_keep=len(s["tokens"]) + 1).logits[0, :-1].float()
        lp = torch.log_softmax(logits, -1).gather(-1, ids[0, -len(s["tokens"]):, None])[:, 0].cpu()
        vl = torch.tensor([x if x is not None else float("nan") for x in s["logprobs"]])
        diffs.append((lp - vl).abs())
    d = torch.cat(diffs) if diffs else torch.zeros(1)
    d = d[torch.isfinite(d)]
    return {"samples": len(samples), "tokens": int(d.numel()), "mean_abs_logprob_diff": round(d.mean().item(), 5),
            "p99_abs_logprob_diff": round(d.quantile(0.99).item(), 5) if d.numel() > 1 else None,
            "max_abs_logprob_diff": round(d.max().item(), 5)}


def main_vllm(cfg: dict, probe: dict, agent: dict, out: Path) -> None:
    """Real agent rollouts with the vLLM server, many at the same time, then the check against transformers."""
    from concurrent.futures import ThreadPoolExecutor

    summary = {"config": cfg, "probe": probe}

    def save():
        (out / "probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    vcfg = probe["vllm"]
    proc, url, summary["server_start_s"], max_len = start_server(cfg["model"], vcfg)
    save()
    model = VllmServerModel(cfg["model"]["family"], cfg["model"]["path"], url, cfg["model"].get("temperature", 1.0),
                            cfg["model"].get("max_new_tokens", 1024), probe.get("logprob_samples", 12), max_len)
    prompt = load_prompt("system", agent["prompt"])
    tasks = select_tasks(probe["split"], probe["tasks"], probe["seed"])
    jobs = [(i, t, g) for i, t in enumerate(tasks) for g in range(probe["group"])]

    def one(job):
        index, task, g = job
        try:
            row, _ = rollout(model, task, prompt, agent)
        except Exception:  # noqa: BLE001
            print(traceback.format_exc(limit=3), file=sys.stderr, flush=True)
            row = {"category": task.category, "difficulty": task.difficulty, "reward": 0.0, "partial_reward": 0.0,
                   "stop_reason": "probe_error", "steps": 0, "tool_calls": 0, "invalid_calls": 0,
                   "input_tokens": 0, "output_tokens": 0, "time_s": 0.0}
        return {"task_index": index, "rollout": g, **row}

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=probe.get("concurrency", 64)) as pool:
        rows = list(pool.map(one, jobs))
    wall = time.perf_counter() - start
    with open(out / "rollouts.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row) + "\n" for row in rows)
    summary["rollouts"] = summarize_groups(rows)
    summary["wall_s"] = round(wall, 1)
    summary["wall_s_per_64_rollouts"] = round(wall * 64 / len(rows), 1)
    print("rollouts", len(rows), "wall", round(wall, 1), "s", flush=True)
    save()
    stop_server(proc)
    try:
        summary["logprob_check"] = check_logprobs(cfg["model"], probe, model.samples)
        print("logprob check", summary["logprob_check"], flush=True)
    except Exception:  # noqa: BLE001
        summary["logprob_check"] = {"error": traceback.format_exc(limit=3)}
        print(summary["logprob_check"]["error"], file=sys.stderr, flush=True)
    save()


# Pipeline: vLLM generates on GPU 0, the trainer computes gradients on GPU 1

def post_json(url: str, body: dict) -> float:
    """Send one POST request. Return the time in seconds."""
    import urllib.request

    start = time.perf_counter()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()
    return time.perf_counter() - start


def random_adapter(peft, scale: float = 1e-3) -> None:
    """Give lora_B small random values. A new adapter has B = 0, and then it does not change the model."""
    torch = __import__("torch")
    with torch.no_grad():
        for name, p in peft.named_parameters():
            if "lora_B" in name:
                p.normal_(0.0, scale)


def main_pipeline(cfg: dict, probe: dict, agent: dict, out: Path) -> None:
    """Measure the real cycle of an RL step with the roles split over two GPUs.

    The trainer never calls an optimizer step. The adapter keeps its random values, so no model learns from test tasks.
    """
    import shutil

    import torch
    from peft import LoraConfig, get_peft_model

    summary = {"config": cfg, "probe": probe}

    def save():
        (out / "probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    vcfg = {**probe["vllm"], "gpus": 0, "lora_rank": probe["lora_rank"]}
    torch.cuda.set_device(1)  # From here, "cuda" means the trainer GPU.
    trainer = make_model({**cfg["model"], "temperature": 0.0, **({"device": "cpu"} if probe.get("offload_ple") else {})})
    if probe.get("offload_ple"):
        summary["offload"] = offload_embeddings(trainer)
    trainer.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    trainer.model.enable_input_require_grads()
    lora = LoraConfig(r=probe["lora_rank"], lora_alpha=2 * probe["lora_rank"], lora_dropout=0.0,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                      exclude_modules=r".*(vision|audio|visual).*", task_type="CAUSAL_LM")
    peft = get_peft_model(trainer.model, lora)
    random_adapter(peft)
    summary["trainable_params"] = sum(p.numel() for p in peft.parameters() if p.requires_grad)
    adapters = out.parent / f"{out.name}-adapters"
    shutil.rmtree(adapters, ignore_errors=True)

    def save_adapter(k: int) -> tuple[str, float]:
        start = time.perf_counter()
        path = adapters / f"v{k}"
        peft.save_pretrained(path)
        return str(path), time.perf_counter() - start

    path, t_save = save_adapter(0)
    proc, url, summary["server_start_s"], max_len = start_server(cfg["model"], vcfg)
    try:
        run_pipeline(summary, save, probe, cfg, agent, peft, trainer, url, max_len, path, t_save, save_adapter)
    except Exception:  # noqa: BLE001  The summary keeps the error, for example an adapter that vLLM does not accept.
        summary["error"] = traceback.format_exc(limit=4)[-3000:]
        print(summary["error"], file=sys.stderr, flush=True)
    finally:
        stop_server(proc)
        shutil.rmtree(adapters, ignore_errors=True)
        save()


def run_pipeline(summary, save, probe, cfg, agent, peft, trainer, url, max_len, path, t_save, save_adapter) -> None:
    from concurrent.futures import ThreadPoolExecutor

    t_load = post_json(url + "/v1/load_lora_adapter", {"lora_name": "v0", "lora_path": path})
    summary["adapter_v0"] = {"save_s": round(t_save, 2), "load_s": round(t_load, 2),
                             "size_mb": round(sum(f.stat().st_size for f in Path(path).iterdir()) / 2**20, 1)}
    print("adapter", summary["adapter_v0"], flush=True)
    save()
    model = VllmServerModel(cfg["model"]["family"], cfg["model"]["path"], url, cfg["model"].get("temperature", 1.0),
                            cfg["model"].get("max_new_tokens", 1024), probe.get("logprob_samples", 12), max_len)
    model.served = "v0"
    prompt = load_prompt("system", agent["prompt"])
    tasks = select_tasks(probe["split"], probe["tasks"], probe["seed"])
    per_step = probe["tasks_per_step"]

    def generate(step: int) -> tuple[list[dict], list[list[dict]], float]:
        chosen = [tasks[(step * per_step + i) % len(tasks)] for i in range(per_step)]
        jobs = [(t, g) for t in chosen for g in range(probe["group"])]

        def one(job):
            try:
                return rollout(model, job[0], prompt, agent)
            except Exception:  # noqa: BLE001
                print(traceback.format_exc(limit=2), file=sys.stderr, flush=True)
                return None, []

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=probe.get("concurrency", 64)) as pool:
            results = list(pool.map(one, jobs))
        rows = [r for r, _ in results if r]
        return rows, [m for _, m in results if m], time.perf_counter() - start

    def train(conversations: list[list[dict]]) -> dict:
        start, done, failed, tokens = time.perf_counter(), 0, 0, 0
        for messages in conversations:
            ids, positions = assistant_positions(trainer, messages, model_tools)
            if not positions:
                continue
            row = backward_once(trainer, peft, ids, positions)
            done += "error" not in row
            failed += "error" in row
            tokens += len(ids)
        return {"sequences": done, "out_of_memory": failed, "tokens": tokens, "time_s": round(time.perf_counter() - start, 1)}

    model_tools = asyncio.run(_list_tools(build_server(load_board(board_path(tasks[0].board)))))
    # vLLM and the trainer must give the same log-probabilities for the adapter.
    rows, conversations, t_gen = generate(0)
    peft.eval()
    summary["logprob_check_lora"] = lora_logprob_check(trainer, peft, model.samples)
    peft.train()
    print("lora logprob check", summary["logprob_check_lora"], flush=True)
    steps = [{"step": 0, "generate_s": round(t_gen, 1), "rollouts": len(rows),
              "success": round(sum(r["reward"] for r in rows) / max(len(rows), 1), 3)}]
    save()
    for k in range(1, probe["steps"] + 1):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=1) as gen_pool:
            future = gen_pool.submit(generate, k)  # vLLM writes step k while the trainer works on step k - 1.
            t_train = train(conversations)
            path, t_save = save_adapter(k)
            t_swap = post_json(url + "/v1/load_lora_adapter", {"lora_name": f"v{k}", "lora_path": path})
            rows, conversations, t_gen = future.result()
        model.served = f"v{k}"
        post_json(url + "/v1/unload_lora_adapter", {"lora_name": f"v{k - 1}"})
        peft.zero_grad(set_to_none=True)
        steps.append({"step": k, "wall_s": round(time.perf_counter() - start, 1), "generate_s": round(t_gen, 1),
                      "train": t_train, "save_s": round(t_save, 2), "swap_s": round(t_swap, 2), "rollouts": len(rows)})
        print("step", steps[-1], flush=True)
        summary["steps"] = steps
        save()


def main_sleep(cfg: dict, probe: dict, agent: dict, out: Path) -> None:
    """Measure an RL step in which vLLM first generates and then frees its GPU, so that both GPUs train.

    vLLM sleeps (level 1: the weights go to CPU memory, the KV cache is freed). A second trainer copy then moves
    to GPU 0. The two copies train on one half of the rollouts each. The trainer never calls an optimizer step.
    """
    import shutil
    from concurrent.futures import ThreadPoolExecutor

    import torch
    from peft import LoraConfig, get_peft_model

    summary = {"config": cfg, "probe": probe}

    def save():
        (out / "probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    lora = LoraConfig(r=probe["lora_rank"], lora_alpha=2 * probe["lora_rank"], lora_dropout=0.0,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                      exclude_modules=r".*(vision|audio|visual).*", task_type="CAUSAL_LM")

    def make_trainer(device: str):
        trainer = make_model({**cfg["model"], "temperature": 0.0, "device": "cpu"})
        if probe.get("offload_ple"):
            offload_embeddings(trainer, device)
        else:
            move_weights(trainer, device)
        trainer.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        trainer.model.enable_input_require_grads()
        peft = get_peft_model(trainer.model, lora)
        return trainer, peft

    torch.cuda.set_device(1)
    trainer1, peft1 = make_trainer("cuda:1")
    random_adapter(peft1)
    trainer0, peft0 = make_trainer("cpu")  # GPU 0 belongs to vLLM until it sleeps.
    from peft import get_peft_model_state_dict, set_peft_model_state_dict

    set_peft_model_state_dict(peft0, {k: v.cpu() for k, v in get_peft_model_state_dict(peft1).items()})
    # Both copies read the same PLE table in CPU memory. One table less saves about 5 GB of RAM.
    tables1 = {n: m for n, m in trainer1.model.named_modules() if isinstance(m, torch.nn.Embedding) and "per_layer" in n}
    for n, m in trainer0.model.named_modules():
        if n in tables1:
            m.weight = tables1[n].weight
    adapters = out.parent / f"{out.name}-adapters"
    shutil.rmtree(adapters, ignore_errors=True)
    peft1.save_pretrained(adapters / "v0")
    vcfg = {**probe["vllm"], "gpus": 0, "lora_rank": probe["lora_rank"], "sleep": True}
    proc, url, summary["server_start_s"], max_len = start_server(cfg["model"], vcfg)
    try:
        post_json(url + "/v1/load_lora_adapter", {"lora_name": "v0", "lora_path": str(adapters / "v0")})
        model = VllmServerModel(cfg["model"]["family"], cfg["model"]["path"], url, cfg["model"].get("temperature", 1.0),
                                cfg["model"].get("max_new_tokens", 1024), 0, max_len)
        model.served = "v0"
        prompt = load_prompt("system", agent["prompt"])
        tasks = select_tasks(probe["split"], probe["tasks"], probe["seed"])
        tools = asyncio.run(_list_tools(build_server(load_board(board_path(tasks[0].board)))))
        per_step, steps = probe["tasks_per_step"], []

        def train_half(trainer, peft, conversations):
            start, done = time.perf_counter(), 0
            torch.cuda.set_device(torch.device(trainer.device))
            for messages in conversations:
                ids, positions = assistant_positions(trainer, messages, tools)
                if positions and "error" not in backward_once(trainer, peft, ids, positions):
                    done += 1
            return done, time.perf_counter() - start

        for k in range(probe["steps"]):
            t = {"step": k}
            start = time.perf_counter()
            chosen = [tasks[(k * per_step + i) % len(tasks)] for i in range(per_step)]
            jobs = [(task, g) for task in chosen for g in range(probe["group"])]
            def one(job):
                try:
                    return rollout(model, job[0], prompt, agent)
                except Exception:  # noqa: BLE001
                    print(traceback.format_exc(limit=2), file=sys.stderr, flush=True)
                    return None, []

            with ThreadPoolExecutor(max_workers=probe.get("concurrency", 64)) as pool:
                results = list(pool.map(one, jobs))
            conversations = [m for _, m in results if m]
            t["generate_s"] = round(time.perf_counter() - start, 1)
            mark = time.perf_counter()
            post_json(url + "/sleep?level=1", {})
            move_weights(trainer0, "cuda:0")
            t["sleep_and_move_s"] = round(time.perf_counter() - mark, 1)
            mark = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(train_half, trainer0, peft0, conversations[0::2])
                b = pool.submit(train_half, trainer1, peft1, conversations[1::2])
                (n0, s0), (n1, s1) = a.result(), b.result()
            t["train_s"] = round(time.perf_counter() - mark, 1)
            t["train_halves_s"] = [round(s0, 1), round(s1, 1)]
            t["sequences"] = n0 + n1
            mark = time.perf_counter()
            # The sum of the two gradients goes to the copy on GPU 1. Here the values only cost time: no step follows.
            grads0 = {n: p.grad for n, p in peft0.named_parameters() if p.grad is not None}
            for n, p in peft1.named_parameters():
                if p.grad is not None and n in grads0:
                    p.grad += grads0[n].to(p.grad.device)
            peft0.zero_grad(set_to_none=True)
            peft1.zero_grad(set_to_none=True)
            move_weights(trainer0, "cpu")
            peft1.save_pretrained(adapters / f"v{k + 1}")
            post_json(url + "/wake_up", {})
            post_json(url + "/v1/load_lora_adapter", {"lora_name": f"v{k + 1}", "lora_path": str(adapters / f"v{k + 1}")})
            model.served = f"v{k + 1}"
            t["sync_wake_swap_s"] = round(time.perf_counter() - mark, 1)
            t["wall_s"] = round(time.perf_counter() - start, 1)
            steps.append(t)
            print("step", t, flush=True)
            summary["steps"] = steps
            save()
    except Exception:  # noqa: BLE001  The summary keeps the error.
        summary["error"] = traceback.format_exc(limit=4)[-3000:]
        print(summary["error"], file=sys.stderr, flush=True)
    finally:
        stop_server(proc)
        shutil.rmtree(adapters, ignore_errors=True)
        save()


def lora_logprob_check(trainer, peft, samples: list[dict]) -> dict:
    torch = trainer.torch
    diffs = []
    for s in samples[:24]:
        ids = torch.tensor([s["prompt"] + s["tokens"]], device=trainer.device)
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            logits = peft(input_ids=ids, logits_to_keep=len(s["tokens"]) + 1).logits[0, :-1].float()
        lp = torch.log_softmax(logits, -1).gather(-1, ids[0, -len(s["tokens"]):, None])[:, 0].cpu()
        vl = torch.tensor([x if x is not None else float("nan") for x in s["logprobs"]])
        diffs.append((lp - vl).abs())
    d = torch.cat(diffs) if diffs else torch.zeros(1)
    d = d[torch.isfinite(d)]
    return {"samples": min(len(samples), 24), "tokens": int(d.numel()), "mean_abs_logprob_diff": round(d.mean().item(), 5),
            "p99_abs_logprob_diff": round(d.quantile(0.99).item(), 5) if d.numel() > 1 else None,
            "max_abs_logprob_diff": round(d.max().item(), 5)}


# Main

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text())
    probe = {**DEFAULTS, **cfg.get("probe", {})}
    agent = {"max_steps": 25, "loop_limit": 3, "error_limit": 5, "prompt": "v3", **cfg.get("agent", {})}
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if probe.get("engine") == "vllm":
        main_vllm(cfg, probe, agent, out)
        return
    if probe.get("engine") == "pipeline":
        main_pipeline(cfg, probe, agent, out)
        return
    if probe.get("engine") == "sleep":
        main_sleep(cfg, probe, agent, out)
        return
    summary = {"config": cfg, "probe": probe}

    def save():
        (out / "probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    import torch

    summary["torch"] = torch.__version__
    summary["gpu"] = torch.cuda.get_device_name() if torch.cuda.is_available() else "cpu"
    start = time.perf_counter()
    model = make_model(cfg["model"])
    if probe.get("offload_ple"):
        summary["offload"] = offload_embeddings(model)
    summary["load_s"] = round(time.perf_counter() - start, 1)
    summary["weights_gb"] = round(torch.cuda.memory_allocated() / 2**30, 2) if torch.cuda.is_available() else 0.0
    prompt = load_prompt("system", agent["prompt"])
    tasks = select_tasks(probe["split"], probe["tasks"], probe["seed"])
    tools = asyncio.run(_list_tools(build_server(load_board(board_path(tasks[0].board)))))
    save()

    messages = [{"role": "system", "content": prompt.text}, {"role": "user", "content": tasks[0].instruction}]
    prompt_text = render(model, messages, tools, True)
    try:
        summary["generation"] = probe_generation(model, prompt_text, probe)
    except Exception:  # noqa: BLE001  A failed part must not stop the next parts.
        summary["generation"] = {"error": traceback.format_exc(limit=3)}
        print(summary["generation"]["error"], file=sys.stderr, flush=True)
    ref = None
    try:
        summary["cache"], ref = probe_cache(model, prompt_text)
    except Exception:  # noqa: BLE001
        summary["cache"] = {"error": traceback.format_exc(limit=3)}
        print(summary["cache"]["error"], file=sys.stderr, flush=True)
    save()

    rows, conversations = [], []
    deadline = time.time() + 60 * probe["rollout_minutes"]
    with open(out / "rollouts.jsonl", "w", encoding="utf-8") as f:
        for index, task in enumerate(tasks):
            if time.time() > deadline:
                break
            for g in range(probe["group"]):
                torch.manual_seed(probe["seed"] * 100000 + index * 100 + g)
                try:
                    row, messages = rollout(model, task, prompt, agent)
                except Exception:  # noqa: BLE001
                    row, messages = {"category": task.category, "difficulty": task.difficulty, "reward": 0.0,
                                     "partial_reward": 0.0, "stop_reason": "probe_error", "steps": 0, "tool_calls": 0,
                                     "invalid_calls": 0, "input_tokens": 0, "output_tokens": 0, "time_s": 0.0}, []
                    print(traceback.format_exc(limit=3), file=sys.stderr, flush=True)
                row = {"task_index": index, "rollout": g, **row}
                rows.append(row)
                f.write(json.dumps(row) + "\n")
                f.flush()
                if messages and any(m["role"] == "assistant" for m in messages):
                    conversations.append(messages)
            print(f"task {index}: rewards {[r['reward'] for r in rows if r['task_index'] == index]}", flush=True)
    summary["rollouts"] = summarize_groups(rows) if rows else {"error": "no rollout"}
    summary["rollout_minutes_used"] = round((time.perf_counter() - start - summary["load_s"]) / 60, 1)
    save()

    try:
        summary["backward"] = probe_backward(model, conversations, tools, probe, ref)
    except Exception:  # noqa: BLE001
        summary["backward"] = {"error": traceback.format_exc(limit=3)}
        print(summary["backward"]["error"], file=sys.stderr, flush=True)
    summary["total_s"] = round(time.perf_counter() - start, 1)
    save()
    print(json.dumps(summary["rollouts"], indent=2), flush=True)


if __name__ == "__main__":
    main()
