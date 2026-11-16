"""Config of an RL run: the sections model, agent, engine and rl, with the defaults of idm-pro-047."""

import copy
import hashlib
import json
from pathlib import Path

import yaml

from src.models import check_config

MODEL_DEFAULTS = {"backend": "transformers", "family": None, "path": None, "adapters": [], "revision": None,
                  "thinking": False, "dtype": "float16", "max_new_tokens": 1024}
AGENT_DEFAULTS = {"prompt": "v3", "max_steps": 25, "loop_limit": 3, "error_limit": 5}
# None means "the value for the family or the engine" (see resolve()).
ENGINE_DEFAULTS = {"name": None, "overlap": None, "concurrency": 64, "port": 8000, "gpu_memory": 0.85,
                   "max_seqs": 64, "batched_tokens": None, "patch": None, "start_minutes": 30,
                   "merged_dir": "/kaggle/temp/merged"}
RL_DEFAULTS = {
    "mode": "train", "split": "train", "eval_split": "validation", "steps": 200, "epochs": 1,
    "tasks_per_step": 8, "group": 8, "tasks": 16, "seed": 0,
    "learning_rate": 1e-5, "warmup_steps": 0, "weight_decay": 0.0, "max_grad_norm": 1.0,
    "lora_rank": 16, "lora_alpha": 32, "lora_dropout": 0.0,
    "loss_type": "dapo", "clip_low": 0.2, "clip_high": 0.28, "reward": "binary", "temperature": 1.0,
    "max_sample_tokens": 8192, "max_context_tokens": None, "max_oom_per_step": 2, "logprob_chunk": 1024,
    "save_every": 25, "keep_checkpoints": 2, "eval_every": 25, "eval_tasks": 40, "deadline_hours": 10.0,
    "memory_check": True, "loss_scale": 1024.0,
}
SECTIONS = {"model": MODEL_DEFAULTS, "agent": AGENT_DEFAULTS, "engine": ENGINE_DEFAULTS, "rl": RL_DEFAULTS}
# These keys can change between the jobs of one run.
RUN_LENGTH_KEYS = ("rl.steps", "rl.deadline_hours")
ENGINES = ("vllm", "transformers")


class ConfigError(ValueError):
    """The config is not valid. The message names the key."""


def resolve(raw: dict) -> dict:
    """Add the defaults and check the keys. An unknown key stops the run, because a typo must not give a silent default."""
    raw = copy.deepcopy(raw or {})
    raw.pop("codename", None)
    for section in raw:
        if section not in SECTIONS:
            raise ConfigError(f"unknown section '{section}' (use {', '.join(SECTIONS)})")
    cfg = {}
    for section, defaults in SECTIONS.items():
        given = raw.get(section) or {}
        for key in given:
            if key not in defaults:
                raise ConfigError(f"unknown key '{section}.{key}'")
        cfg[section] = {**copy.deepcopy(defaults), **given}
    model, engine, rl = cfg["model"], cfg["engine"], cfg["rl"]
    if not model["family"] or not model["path"]:
        raise ConfigError("the config must give model.family and model.path")
    if model["backend"] != "transformers":
        raise ConfigError("an RL run needs model.backend: transformers")
    check_config({k: v for k, v in model.items() if k != "adapters"})
    engine["name"] = engine["name"] or ("transformers" if model["family"] == "gemma4" else "vllm")
    if engine["name"] not in ENGINES:
        raise ConfigError(f"unknown engine.name '{engine['name']}' (use {', '.join(ENGINES)})")
    if engine["overlap"] is None:
        engine["overlap"] = engine["name"] == "vllm"
    if engine["overlap"] and engine["name"] != "vllm":
        raise ConfigError("engine.overlap needs the engine vllm")
    if engine["patch"] is None:
        engine["patch"] = model["family"] == "gemma4"
    if rl["max_context_tokens"] is None:
        rl["max_context_tokens"] = rl["max_sample_tokens"]
    for key, allowed in (("mode", ("train", "measure")), ("reward", ("binary", "partial")), ("loss_type", ("dapo",))):
        if rl[key] not in allowed:
            raise ConfigError(f"rl.{key} must be one of {', '.join(allowed)}, not '{rl[key]}'")
    if rl["mode"] == "train" and "test" in (rl["split"], rl["eval_split"]):
        raise ConfigError("the split test is allowed only in rl.mode: measure")
    if rl["group"] < 2:
        raise ConfigError("rl.group must be 2 or more")
    return cfg


def load(path: str | Path) -> dict:
    return resolve(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _flat(cfg: dict) -> dict:
    return {f"{s}.{k}": v for s, section in cfg.items() for k, v in section.items()}


def config_hash(cfg: dict) -> str:
    kept = {k: v for k, v in _flat(cfg).items() if k not in RUN_LENGTH_KEYS}
    return hashlib.sha256(json.dumps(kept, sort_keys=True, default=str).encode()).hexdigest()[:16]


def differences(a: dict, b: dict) -> list[str]:
    """The keys with another value, without the keys of the run length."""
    fa, fb = _flat(a), _flat(b)
    return sorted(k for k in set(fa) | set(fb) if k not in RUN_LENGTH_KEYS and fa.get(k) != fb.get(k))
