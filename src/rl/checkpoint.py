"""Checkpoints of an RL run (design Decision 9).

A checkpoint is the folder `checkpoints/step-<N>/` with these files:
- `adapter/`: the LoRA adapter;
- `state.json`: the step, the position in the task order, the best validation score and the config;
- `optimizer.pt`: the optimizer, the schedule and the random states. Only the last checkpoints keep it.
"""

import json
import random
import shutil
from pathlib import Path

import torch

STATE, OPTIMIZER = "state.json", "optimizer.pt"


def step_of(folder: Path) -> int:
    return int(folder.name.split("-")[-1])


def random_states() -> dict:
    states = {"python": random.getstate(), "torch": torch.get_rng_state()}
    if torch.cuda.is_available():
        states["cuda"] = torch.cuda.get_rng_state_all()
    return states


def set_random_states(states: dict) -> None:
    random.setstate(states["python"])
    torch.set_rng_state(states["torch"])
    if "cuda" in states and torch.cuda.is_available() and len(states["cuda"]) == torch.cuda.device_count():
        torch.cuda.set_rng_state_all(states["cuda"])


def save(output: Path, step: int, write_adapter, optimizer, scheduler, state: dict, keep: int, extra: dict | None = None) -> Path:
    """Write a checkpoint. `write_adapter(folder)` writes the adapter. Remove the optimizer state of old checkpoints."""
    root = Path(output) / "checkpoints"
    folder = root / f"step-{step}"
    tmp = root / f".step-{step}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    write_adapter(tmp / "adapter")
    torch.save({"optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict() if scheduler else None,
                "random": random_states(), **(extra or {})}, tmp / OPTIMIZER)
    (tmp / STATE).write_text(json.dumps({**state, "step": step}, indent=2, default=str), encoding="utf-8")
    # A stopped write must not leave a checkpoint without its files, so the folder gets its name only at the end.
    shutil.rmtree(folder, ignore_errors=True)
    tmp.rename(folder)
    with_optimizer = sorted((f for f in root.glob("step-*") if (f / OPTIMIZER).exists()), key=step_of)
    for old in with_optimizer[:-keep] if keep > 0 else with_optimizer:
        (old / OPTIMIZER).unlink()
    return folder


def find(path: str | Path) -> Path:
    """The checkpoint to continue from: the folder itself, or the last checkpoint with an optimizer state below it."""
    path = Path(path)
    if (path / STATE).exists() and (path / OPTIMIZER).exists():
        return path
    found = [f.parent for f in path.rglob(f"step-*/{OPTIMIZER}") if not f.parent.name.startswith(".")]
    if not found:
        raise FileNotFoundError(f"no checkpoint with an optimizer state in {path}")
    return max(found, key=step_of)


def load(folder: Path, optimizer, scheduler) -> dict:
    """Read the optimizer, the schedule and the random states. Return the state and the extra values."""
    folder = Path(folder)
    blob = torch.load(folder / OPTIMIZER, map_location="cpu", weights_only=False)
    optimizer.load_state_dict(blob["optimizer"])
    if scheduler is not None and blob.get("scheduler") is not None:
        scheduler.load_state_dict(blob["scheduler"])
    set_random_states(blob["random"])
    state = json.loads((folder / STATE).read_text(encoding="utf-8"))
    return {"state": state, "extra": {k: v for k, v in blob.items() if k not in ("optimizer", "scheduler", "random")}}
