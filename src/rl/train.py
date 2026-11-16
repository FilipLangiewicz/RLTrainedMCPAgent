"""RL run: GRPO on the tasks of the simulator with a new LoRA adapter (issue idm-pro-048).

Usage: python -m src.rl.train <config.yaml> --output <folder> [--resume <folder>]

The output folder gets only small files: run.json, metrics.jsonl, rollouts.jsonl, status.json, and the adapters
in checkpoints/, best/ and final/. The run never ends with an error code, so that Kaggle keeps the output.
"""

import argparse
import gc
import json
import math
import platform
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from src.models import check_adapters, load_prompt
from src.rl import checkpoint
from src.rl.config import ConfigError, differences, load
from src.rl.grpo import advantages, policy_loss
from src.rl.rollouts import GOOD, group_stats, run_rollouts, select_tasks
from src.rl.tokens import build_samples
from src.tasks import load_tasks

ROOT = Path(__file__).resolve().parents[2]


class MemoryCheckError(RuntimeError):
    """The backward pass of a sample of rl.max_sample_tokens tokens does not fit in the GPU memory."""


# Records

class Records:
    def __init__(self, output: Path):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.status = {"status": "running", "step": 0}

    def write_json(self, name: str, data: dict) -> None:
        (self.output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def append(self, name: str, rows: list[dict]) -> None:
        with self.lock, open(self.output / name, "a", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)

    def set_status(self, **values) -> None:
        self.status.update(values, time=datetime.now(UTC).isoformat(timespec="seconds"))
        self.write_json("status.json", self.status)


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def versions() -> dict:
    import os

    result = {"python": platform.python_version()}
    for name in ("torch", "transformers", "peft"):
        try:
            result[name] = __import__(name).__version__
        except ImportError:
            result[name] = None
    python = os.environ.get("VLLM_PYTHON")
    if python:
        done = subprocess.run([python, "-c", "import vllm; print(vllm.__version__)"], capture_output=True, text=True,
                              check=False)
        result["vllm"] = done.stdout.strip().splitlines()[-1] if done.returncode == 0 and done.stdout.strip() else None
    try:
        import torch

        result["gpus"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    except ImportError:
        result["gpus"] = []
    return result


def memory(devices: list[str] = ()) -> dict:
    """The peak GPU memory of the trainer devices since the last call, and the CPU memory.

    Only the trainer devices count: a query of the vLLM GPU from this process can take memory there.
    """
    result = {}
    for device in devices:
        if str(device).startswith("cuda"):
            import torch

            i = torch.device(device).index or 0
            result[f"gpu{i}_peak_gb"] = round(torch.cuda.max_memory_allocated(i) / 2**30, 2)
            torch.cuda.reset_peak_memory_stats(i)
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS", "VmHWM")):
                result[line.split(":")[0].lower() + "_gb"] = round(int(line.split()[1]) / 2**20, 2)
    except OSError:
        pass
    return result


# Task order

def epoch_order(count: int, seed: int, epoch: int) -> list[int]:
    order = list(range(count))
    random.Random(seed * 1000 + epoch).shuffle(order)
    return order


def next_tasks(count: int, seed: int, epochs: int, epoch: int, position: int, k: int) -> tuple[list[int], int, int] | None:
    """The task indices of the next step and the new (epoch, position). None when all epochs are done."""
    if epoch >= epochs:
        return None
    picks = []
    while len(picks) < k and epoch < epochs:
        order = epoch_order(count, seed, epoch)
        take = order[position: position + k - len(picks)]
        picks += take
        position += len(take)
        if position >= count:
            epoch, position = epoch + 1, 0
    return (picks, epoch, position) if picks else None


# Update

def split_samples(samples: list, parts: int) -> list[list]:
    """Give each copy about the same number of tokens."""
    buckets, sizes = [[] for _ in range(parts)], [0] * parts
    for s in sorted(samples, key=lambda s: -len(s.ids)):
        i = sizes.index(min(sizes))
        buckets[i].append(s)
        sizes[i] += len(s.ids)
    return buckets


def is_oom(e: BaseException) -> bool:
    import torch

    return isinstance(e, torch.cuda.OutOfMemoryError) or "out of memory" in str(e).lower()


def backward_part(policy, samples: list, total_tokens: int, rl: dict, scale: float) -> dict:
    """The gradients of the samples of one copy. An OOM of one sample skips this sample only."""
    import torch

    if torch.cuda.is_available() and str(policy.device).startswith("cuda"):
        torch.cuda.set_device(torch.device(policy.device))
    params = policy.parameters()
    total = [torch.zeros_like(p, dtype=torch.float32) for p in params]
    stats = {"samples": 0, "oom": 0, "loss_sum": 0.0, "tokens": 0, "clipped": 0, "diff_sum": 0.0, "diff_max": 0.0}
    policy.model.train()
    try:
        for s in samples:
            failed = False
            try:
                logp = policy.logprobs(s.ids, s.mask)
                old = torch.tensor([lp for p, (m, lp) in enumerate(zip(s.mask, s.old_logprobs)) if m and p > 0],
                                   device=logp.device, dtype=torch.float32)
                loss, st = policy_loss(logp, old, s.advantage, rl["clip_low"], rl["clip_high"])
                (loss * (scale / total_tokens)).backward()
                for t, p in zip(total, params):
                    if p.grad is not None:
                        t += p.grad
                stats["samples"] += 1
                stats["loss_sum"] += float(loss.detach())
                stats["tokens"] += st["tokens"]
                stats["clipped"] += st["clipped"]
                stats["diff_sum"] += st["logprob_diff_sum"]
                stats["diff_max"] = max(stats["diff_max"], st["logprob_diff_max"])
            except Exception as e:
                if not is_oom(e):
                    raise
                stats["oom"] += 1
                failed = True
                print(f"out of memory in a sample of {len(s.ids)} tokens", flush=True)
            finally:
                for p in params:
                    p.grad = None
                loss = logp = None
            if failed:
                policy.free_memory()
    finally:
        policy.model.eval()
    for t, p in zip(total, params):
        p.grad = t
    return stats


class Updater:
    """The GRPO update over one or two model copies. The last copy has the optimizer."""

    def __init__(self, policies: list, rl: dict, optimizer, scheduler):
        self.policies, self.rl, self.optimizer, self.scheduler = policies, rl, optimizer, scheduler
        self.loss_scale = rl["loss_scale"]
        self.good_steps = 0

    def update(self, rollouts: list) -> dict:
        import torch

        rl = self.rl
        adv, gstats = advantages([r.reward for r in rollouts], [r.group for r in rollouts])
        samples, dropped = [], 0
        for r, a in zip(rollouts, adv):
            if a is None or a == 0:
                continue
            made, d = build_samples(r.turns, rl["max_sample_tokens"], a)
            samples += made
            dropped += d
        tokens = sum(s.model_tokens for s in samples)
        result = {**{k: v for k, v in gstats.items()}, "samples": len(samples), "model_tokens": tokens,
                  "dropped_turns": dropped, "update": False, "oom": 0}
        if not samples or tokens == 0:
            return result
        parts = split_samples(samples, len(self.policies))
        with ThreadPoolExecutor(max_workers=len(self.policies)) as pool:
            stats = list(pool.map(lambda x: backward_part(x[0], x[1], tokens, rl, self.loss_scale),
                                  zip(self.policies, parts)))
        main = self.policies[-1]
        params = main.parameters()
        for other in self.policies[:-1]:
            for p, q in zip(params, other.parameters()):
                p.grad += q.grad.to(p.device)
                q.grad = None
        oom = sum(s["oom"] for s in stats)
        done_tokens = sum(s["tokens"] for s in stats)
        result.update(oom=oom, loss=round(sum(s["loss_sum"] for s in stats) / tokens, 6),
                      clip_share=round(sum(s["clipped"] for s in stats) / max(done_tokens, 1), 5),
                      logprob_diff_mean=round(sum(s["diff_sum"] for s in stats) / max(done_tokens, 1), 5),
                      logprob_diff_max=round(max(s["diff_max"] for s in stats), 5), loss_scale=self.loss_scale)
        if oom > rl["max_oom_per_step"]:
            result["cancelled"] = "too many out-of-memory errors"
        else:
            for p in params:
                p.grad /= self.loss_scale
            norm = float(torch.nn.utils.clip_grad_norm_(params, rl["max_grad_norm"]))
            result["grad_norm"] = round(norm, 5) if math.isfinite(norm) else str(norm)
            if not math.isfinite(norm):
                # fp16 can give an infinite gradient. A smaller loss scale avoids it in the next step.
                result["nonfinite_grad"] = True
                self.loss_scale = max(self.loss_scale / 2, 1.0)
            else:
                self.optimizer.step()
                if self.scheduler is not None:
                    self.scheduler.step()
                result["update"] = True
                self.good_steps += 1
                if self.good_steps % 50 == 0:
                    self.loss_scale = min(self.loss_scale * 2, 2.0**16)
        for p in params:
            p.grad = None
        result["lora_sync_max_diff"] = self.sync()
        return result

    def sync(self) -> float | None:
        """Copy the LoRA weights of the main copy to the other copies. Return the largest difference after the copy."""
        if len(self.policies) < 2:
            return None
        main = self.policies[-1].parameters()
        worst = 0.0
        for other in self.policies[:-1]:
            for p, q in zip(main, other.parameters()):
                q.data.copy_(p.data.to(q.device))
                worst = max(worst, float((p.data - q.data.to(p.device)).abs().max()))
        return worst


def memory_check(policy, length: int) -> dict:
    """One forward and backward pass with a sequence of `length` tokens. Raise MemoryCheckError on an OOM."""
    import torch

    if torch.cuda.is_available() and str(policy.device).startswith("cuda"):
        torch.cuda.set_device(torch.device(policy.device))
        torch.cuda.reset_peak_memory_stats()
    vocab = len(policy.tokenizer)
    ids = [random.Random(length).randrange(100, vocab - 1) for _ in range(length)]
    mask = [0] * (length - min(1024, length - 1)) + [1] * min(1024, length - 1)
    start = time.perf_counter()
    policy.model.train()
    try:
        logp = policy.logprobs(ids, mask)
        (-logp.mean()).backward()
    except Exception as e:
        if not is_oom(e):
            raise
        raise MemoryCheckError(f"out of memory in the memory check with {length} tokens on {policy.device}: "
                               f"lower rl.max_sample_tokens ({str(e)[:300]})") from None
    finally:
        policy.model.eval()
        for p in policy.parameters():
            p.grad = None
        logp = None
        policy.free_memory()
    peak = round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else 0.0
    return {"device": str(policy.device), "tokens": length, "peak_gb": peak, "time_s": round(time.perf_counter() - start, 1)}


# The loop

class Loop:
    """The loop of steps. The model parts are methods, so that a test can replace them."""

    def __init__(self, cfg: dict, records: Records, clock=time.time):
        self.cfg, self.rl, self.records, self.clock = cfg, cfg["rl"], records, clock
        self.started = clock()
        self.step, self.epoch, self.position = 0, 0, 0
        self.best_score, self.best_step = None, None
        self.saved_step = 0
        self.task_count = 0
        self.devices: list[str] = []

    def past_deadline(self) -> bool:
        return self.clock() - self.started > 3600 * self.rl["deadline_hours"]

    # Model parts
    def generate(self, picks: list[int]) -> tuple[list, float]:
        raise NotImplementedError

    def update(self, rollouts: list) -> dict:
        raise NotImplementedError

    def publish(self) -> None:
        """Give the new adapter to the engine."""

    def validate(self) -> dict:
        return {}

    def save_checkpoint(self) -> None:
        self.saved_step = self.step

    def save_final(self) -> None:
        pass

    def cancel_generation(self, future) -> None:
        future.result()

    def state(self) -> dict:
        return {"step": self.step, "epoch": self.epoch, "position": self.position,
                "best_score": self.best_score, "best_step": self.best_step}

    def run(self) -> str:
        rl = self.rl

        def plan(epoch, position):
            if self.step >= rl["steps"]:
                return None
            return next_tasks(self.task_count, rl["seed"], rl["epochs"], epoch, position, rl["tasks_per_step"])

        overlap = self.cfg["engine"]["overlap"]
        current = plan(self.epoch, self.position)
        pool = ThreadPoolExecutor(max_workers=1) if overlap else None
        pending = pool.submit(self.generate, current[0]) if overlap and current else None
        status = "complete"
        try:
            while current is not None:
                rollouts, t_gen = pending.result() if overlap else self.generate(current[0])
                pending = None
                picks, epoch, position = current
                self.step += 1
                nxt = plan(epoch, position)
                if overlap and nxt and not self.past_deadline():
                    # vLLM samples step k + 1 while the trainer does the update of step k (design Decision 6).
                    pending = pool.submit(self.generate, nxt[0])
                start = time.perf_counter()
                row = {"kind": "step", "step": self.step, "epoch": self.epoch, "tasks": len(picks),
                       **group_stats(rollouts)}
                row.update(self.update(rollouts))
                self.epoch, self.position = epoch, position
                self.publish()
                row.update(generate_s=round(t_gen, 1), update_s=round(time.perf_counter() - start, 1),
                           elapsed_h=round((self.clock() - self.started) / 3600, 3), **memory(self.devices))
                self.records.append("metrics.jsonl", [row])
                self.records.append("rollouts.jsonl", [{"step": self.step, **r.row(rl["split"] != "test")}
                                                        for r in rollouts])
                print("step", json.dumps({k: row.get(k) for k in ("step", "mean_reward", "mixed_share", "loss",
                                                                  "grad_norm", "samples", "update")}), flush=True)
                self.records.set_status(status="running", step=self.step)
                if rl["eval_every"] and self.step % rl["eval_every"] == 0:
                    self.run_validation()
                if self.step % rl["save_every"] == 0:
                    self.save_checkpoint()
                if nxt is not None and self.past_deadline():
                    status = "deadline"
                    break
                current = nxt
        finally:
            if pending is not None:
                self.cancel_generation(pending)
            if pool is not None:
                pool.shutdown(wait=True)
        if self.saved_step != self.step:
            self.save_checkpoint()
        self.save_final()
        return status

    def run_validation(self) -> None:
        start = time.perf_counter()
        result = self.validate()
        if not result:
            return
        score = result["score"]
        if self.best_score is None or score > self.best_score:
            self.best_score, self.best_step = score, self.step
            self.save_best()
        row = {"kind": "validation", "step": self.step, **result, "best_score": self.best_score,
               "best_step": self.best_step, "time_s": round(time.perf_counter() - start, 1)}
        self.records.append("metrics.jsonl", [row])
        print("validation", json.dumps(row), flush=True)

    def save_best(self) -> None:
        pass


class ModelLoop(Loop):
    """The loop with the real engine and the trainer copies."""

    def __init__(self, cfg, records, engine, policies, tasks, val_tasks, prompt):
        super().__init__(cfg, records)
        self.engine, self.policies, self.tasks, self.val_tasks, self.prompt = engine, policies, tasks, val_tasks, prompt
        self.task_count = len(tasks)
        self.main = policies[-1]
        self.devices = [p.device for p in policies]
        import torch

        self.optimizer = torch.optim.AdamW(self.main.parameters(), lr=self.rl["learning_rate"],
                                           weight_decay=self.rl["weight_decay"])
        warmup = self.rl["warmup_steps"]
        self.scheduler = torch.optim.lr_scheduler.LambdaLR(
            self.optimizer, lambda s: min(1.0, (s + 1) / warmup) if warmup else 1.0)
        self.updater = Updater(policies, self.rl, self.optimizer, self.scheduler)
        self.live = Path(records.output) / ".live"

    def generate(self, picks):
        start = time.perf_counter()
        jobs = [(self.tasks[i], g) for g, i in enumerate(picks) for _ in range(self.rl["group"])]
        rollouts = run_rollouts(self.engine, jobs, self.prompt, self.cfg["agent"], self.rl["reward"])
        failed = sum(r.engine_error is not None and not r.engine_error.startswith("Cancelled") for r in rollouts)
        if failed > len(rollouts) / 2:
            raise RuntimeError(f"the engine failed in {failed} of {len(rollouts)} rollouts: "
                               f"{next(r.engine_error for r in rollouts if r.engine_error)}")
        # A failure of the engine in one rollout removes its full group from the update (design Decision 8).
        bad = {r.group for r in rollouts if r.engine_error is not None}
        for r in rollouts:
            if r.group in bad:
                r.reward = None
        return rollouts, time.perf_counter() - start

    def update(self, rollouts):
        return self.updater.update(rollouts)

    def publish(self):
        if not hasattr(self.engine, "url"):
            return
        folder = self.live / f"step-{self.step}"
        self.main.save_adapter(folder)
        self.engine.load_adapter(folder)
        for old in self.live.glob("step-*"):
            if old != folder:
                shutil.rmtree(old, ignore_errors=True)

    def validate(self):
        jobs = [(t, i) for i, t in enumerate(self.val_tasks)]
        rollouts = run_rollouts(self.engine, jobs, self.prompt, self.cfg["agent"], "binary", temperature=0.0)
        stats = group_stats(rollouts)
        score = sum(r.grade in GOOD for r in rollouts) / max(len(rollouts), 1)
        return {"score": round(score, 4), "tasks": len(rollouts), "mean_reward": stats["mean_reward"],
                "context_limit": stats["context_limit"], "stop_reasons": stats["stop_reasons"]}

    def save_best(self):
        shutil.rmtree(self.records.output / "best", ignore_errors=True)
        self.main.save_adapter(self.records.output / "best")
        (self.records.output / "best" / "step.json").write_text(json.dumps({"step": self.step, "score": self.best_score}))

    def save_checkpoint(self):
        checkpoint.save(self.records.output, self.step, self.main.save_adapter, self.optimizer, self.scheduler,
                        {**self.state(), "config": self.cfg}, self.rl["keep_checkpoints"],
                        {"loss_scale": self.updater.loss_scale, "good_steps": self.updater.good_steps})
        self.saved_step = self.step

    def save_final(self):
        shutil.rmtree(self.records.output / "final", ignore_errors=True)
        self.main.save_adapter(self.records.output / "final")
        shutil.rmtree(self.live, ignore_errors=True)

    def cancel_generation(self, future):
        self.engine.cancel.set()
        try:
            future.result()
        except Exception as e:  # noqa: BLE001  The stopped rollouts of the next step do not count.
            print(f"stopped generation: {type(e).__name__}", flush=True)
        self.engine.cancel.clear()

    def resume(self, folder: Path) -> dict:
        found = checkpoint.find(folder)
        loaded = checkpoint.load(found, self.optimizer, self.scheduler)
        state = loaded["state"]
        changed = differences(state["config"], self.cfg)
        if changed:
            raise ConfigError(f"the config differs from the checkpoint {found} in: {', '.join(changed)}")
        self.main.load_adapter_folder(found / "adapter")
        self.updater.sync()
        self.step, self.epoch, self.position = state["step"], state["epoch"], state["position"]
        self.best_score, self.best_step = state.get("best_score"), state.get("best_step")
        self.saved_step = self.step
        self.updater.loss_scale = loaded["extra"].get("loss_scale", self.updater.loss_scale)
        self.updater.good_steps = loaded["extra"].get("good_steps", 0)
        self.publish()
        return {"checkpoint": str(found), "step": self.step, "epoch": self.epoch, "position": self.position}


# Setup

def gpu_count() -> int:
    try:
        import torch

        return torch.cuda.device_count()
    except ImportError:
        return 0


def build(cfg: dict, output: Path, records: Records, run: dict):
    """Load the trainer copies and start the engine. Return the engine and the copies."""
    import torch

    from src.rl.engines import TransformersEngine, VllmEngine
    from src.rl.policy import Policy

    model, rl, engine_cfg = cfg["model"], cfg["rl"], cfg["engine"]
    train = rl["mode"] == "train"
    gpus = gpu_count()
    start = time.perf_counter()
    if engine_cfg["name"] == "vllm":
        trainer_device = "cuda:1" if gpus > 1 else ("cuda:0" if gpus else "cpu")
        if trainer_device.startswith("cuda"):
            torch.cuda.set_device(torch.device(trainer_device))
        served = model["path"]
        policies = []
        if train or model["adapters"]:
            policy = Policy(model, rl, trainer_device, train=train,
                            save_merged_to=engine_cfg["merged_dir"] if model["adapters"] else None)
            if model["adapters"]:
                served = engine_cfg["merged_dir"]
            if train:
                policies = [policy]
            else:
                del policy
                gc.collect()
                torch.cuda.empty_cache()
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model["path"], local_files_only=Path(model["path"]).is_dir())
        engine = VllmEngine(cfg, tokenizer, served, gpu=0)
        run["load_s"] = round(time.perf_counter() - start, 1)
        engine.start()
    else:
        devices = [f"cuda:{i}" for i in range(gpus)] or ["cpu"]
        main = Policy(model, rl, devices[-1], train=train)
        policies = [main]
        if len(devices) > 1:
            shared = main.tables() if main.offload else None
            policies = [Policy(model, rl, devices[0], train=train, shared_tables=shared), main]
        engine = TransformersEngine(cfg, policies)
        run["load_s"] = round(time.perf_counter() - start, 1)
        if train:
            Updater(policies, rl, None, None).sync()
    run["engine"] = engine.describe()
    run["trainable_params"] = sum(p.numel() for p in policies[-1].parameters()) if policies and train else 0
    records.write_json("run.json", run)
    return engine, policies if train else []


def run_measure(cfg: dict, records: Records, engine, prompt) -> None:
    rl = cfg["rl"]
    tasks = select_tasks(load_tasks(rl["split"]), rl["tasks"], rl["seed"])
    jobs = [(t, g) for g, t in enumerate(tasks) for _ in range(rl["group"])]
    start = time.perf_counter()
    rollouts = run_rollouts(engine, jobs, prompt, cfg["agent"], rl["reward"])
    wall = time.perf_counter() - start
    stats = group_stats(rollouts)
    records.append("rollouts.jsonl", [r.row(rl["split"] != "test") for r in rollouts])
    records.append("metrics.jsonl", [{"kind": "measure", "split": rl["split"], "tasks": len(tasks), **stats,
                                      "wall_s": round(wall, 1), "wall_s_per_64_rollouts": round(wall * 64 / max(len(rollouts), 1), 1),
                                      **memory([p.device for p in getattr(engine, "policies", [])])}])
    print("measure", json.dumps(stats), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config")
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", help="a checkpoint folder or the output folder of an earlier job")
    args = parser.parse_args(argv)
    records = Records(Path(args.output))
    records.set_status(status="running", step=0)
    engine, loop = None, None
    try:
        cfg = load(args.config)
        rl = cfg["rl"]
        run = {"config": cfg, "git_commit": git_commit(), **versions(), "resume": args.resume,
               "start": datetime.now(UTC).isoformat(timespec="seconds")}
        records.write_json("run.json", run)
        prompt = load_prompt("system", cfg["agent"]["prompt"])
        check_adapters(cfg["model"]["path"], cfg["model"]["adapters"])
        if rl["mode"] == "train":
            tasks, val_tasks = load_tasks(rl["split"]), load_tasks(rl["eval_split"])
            if not tasks:
                raise ConfigError(f"the split {rl['split']} has no tasks")
            val_tasks = select_tasks(val_tasks, rl["eval_tasks"], rl["seed"])
        engine, policies = build(cfg, Path(args.output), records, run)
        if rl["mode"] == "measure":
            run_measure(cfg, records, engine, prompt)
            records.set_status(status="complete", step=0)
            return 0
        if rl["memory_check"]:
            run["memory_check"] = [memory_check(p, rl["max_sample_tokens"]) for p in policies]
            records.write_json("run.json", run)
            print("memory check", run["memory_check"], flush=True)
        loop = ModelLoop(cfg, records, engine, policies, tasks, val_tasks, prompt)
        if args.resume:
            run["resumed_from"] = loop.resume(Path(args.resume))
            records.write_json("run.json", run)
            print("resume", run["resumed_from"], flush=True)
        status = loop.run()
        records.set_status(status=status, step=loop.step, elapsed_h=round((time.time() - loop.started) / 3600, 3))
    except Exception as e:  # noqa: BLE001  Kaggle deletes the output of a failed kernel, so the run never fails.
        error = traceback.format_exc(limit=6)
        print(error, file=sys.stderr, flush=True)
        step = loop.step if loop else 0
        records.set_status(status="error", step=step, error=f"{type(e).__name__}: {e}"[:2000], traceback=error[-4000:])
        if loop is not None and loop.step > loop.saved_step:
            try:
                loop.save_checkpoint()
                records.set_status(checkpoint=loop.step)
            except Exception:  # noqa: BLE001
                print(traceback.format_exc(limit=3), file=sys.stderr, flush=True)
    finally:
        if engine is not None:
            engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
