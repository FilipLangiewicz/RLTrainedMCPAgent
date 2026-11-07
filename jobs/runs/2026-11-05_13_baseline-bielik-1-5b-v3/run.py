"""Baseline of one model on the 200 test tasks.

A model that fits on one GPU runs with one process on each GPU (each process does one half of the tasks).
A model that does not fit runs with one process on both GPUs.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "06-e1-baselines"
CLONE = "/tmp/repo"  # Not in the output folder, so the clone is not an output.
JOB = "2026-11-05_13_baseline-bielik-1-5b-v3"
CODENAME = "baseline-bielik-1-5b-v3"
SHARDS = 2  # 2: one process on each GPU. 1: one process (with device "auto" it uses both GPUs).
DEADLINE_S = 10.5 * 3600  # Stop the processes before the 12-hour limit of the session.
OUTPUT = Path("/kaggle/working") / CODENAME

import torch

assert torch.cuda.device_count() == 2, "this job needs 2 GPUs (T4 x2): check the phone verification of the account"
print("torch", torch.__version__, "cuda", torch.version.cuda, flush=True)

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)

import yaml

cfg = yaml.safe_load(Path(f"{CLONE}/jobs/runs/{JOB}/{CODENAME}.yaml").read_text())
# The mount path of a Kaggle Model can change, so find the weights by the slug and config.json.
slug = Path(cfg["model"]["path"]).parts[3]
weights = sorted(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts)[0].parent
cfg["model"]["path"] = str(weights)
manifest = weights / "manifest.json"
if manifest.is_file():
    cfg["model"]["revision"] = json.loads(manifest.read_text())["commit"]
config_file = Path("/tmp") / f"{CODENAME}.yaml"
config_file.write_text(yaml.safe_dump(cfg))
print("weights", weights, "revision", cfg["model"].get("revision"), flush=True)

shards = [OUTPUT / "shards" / str(i) for i in range(SHARDS)] if SHARDS > 1 else [OUTPUT]
processes = []
for i, shard in enumerate(shards):
    command = [sys.executable, "-m", "src.evaluate", str(config_file), "--output", str(shard)]
    env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
    if SHARDS > 1:
        command += ["--shard", f"{i}/{SHARDS}"]
        env["CUDA_VISIBLE_DEVICES"] = str(i)  # Each process sees only its GPU as "cuda".
    processes.append(subprocess.Popen(command, cwd=CLONE, env=env))
end = time.time() + DEADLINE_S
codes = []
for p in processes:
    try:
        codes.append(p.wait(timeout=max(0.0, end - time.time())))
    except subprocess.TimeoutExpired:
        p.kill()
        codes.append("timeout")
print("exit codes", codes, flush=True)

# An error of the kernel deletes all output. Thus a failed process does not stop the job.
if not all(code == 0 for code in codes):
    print("FAILED: not all processes are complete. The results of each process are in", OUTPUT, flush=True)
elif SHARDS > 1:
    subprocess.run([sys.executable, "-m", "src.evaluate", "--merge", *map(str, shards), "--output", str(OUTPUT)], cwd=CLONE, check=True)
