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


def probe_backward(model, conversations: list[list[dict]], tools: list[dict], cfg: dict) -> dict:
    peft, info = lora_model(model, cfg["lora_rank"])
    print("lora", info, flush=True)
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
    summary = {"config": cfg, "probe": probe}

    def save():
        (out / "probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    import torch

    summary["torch"] = torch.__version__
    summary["gpu"] = torch.cuda.get_device_name() if torch.cuda.is_available() else "cpu"
    start = time.perf_counter()
    model = make_model(cfg["model"])
    summary["load_s"] = round(time.perf_counter() - start, 1)
    summary["weights_gb"] = gpu_gb(torch)
    prompt = load_prompt("system", agent["prompt"])
    tasks = select_tasks(probe["split"], probe["tasks"], probe["seed"])
    tools = asyncio.run(_list_tools(build_server(load_board(board_path(tasks[0].board)))))
    save()

    try:
        messages = [{"role": "system", "content": prompt.text}, {"role": "user", "content": tasks[0].instruction}]
        summary["generation"] = probe_generation(model, render(model, messages, tools, True), probe)
    except Exception:  # noqa: BLE001  A failed part must not stop the next parts.
        summary["generation"] = {"error": traceback.format_exc(limit=3)}
        print(summary["generation"]["error"], file=sys.stderr, flush=True)
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
        summary["backward"] = probe_backward(model, conversations, tools, probe)
    except Exception:  # noqa: BLE001
        summary["backward"] = {"error": traceback.format_exc(limit=3)}
        print(summary["backward"]["error"], file=sys.stderr, flush=True)
    summary["total_s"] = round(time.perf_counter() - start, 1)
    save()
    print(json.dumps(summary["rollouts"], indent=2), flush=True)


if __name__ == "__main__":
    main()
