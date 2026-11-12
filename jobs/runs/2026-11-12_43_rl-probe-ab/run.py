"""RL probe (src/rl_probe.py) of the cost and the signal of RL. It only measures. It does not train."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "07-rl-method"
CLONE = "/tmp/repo"  # Not in the output folder, so the clone is not an output.
JOB = "2026-11-12_43_rl-probe-ab"
# Each stage runs its codenames at the same time. A GPU of None gives the process both GPUs.
STAGES = [[("rl-probe-a", 0), ("rl-probe-b", 1)]]
DEADLINE_S = 3 * 3600

import torch

assert torch.cuda.device_count() == 2, "this job needs 2 GPUs (T4 x2): check the phone verification of the account"
print("torch", torch.__version__, "cuda", torch.version.cuda, flush=True)

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)
# The Kaggle image has torchao 0.10. PEFT 0.21 stops with an ImportError for torchao below 0.16. The project does not use torchao.
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=True)

import yaml


def config_file(codename: str) -> Path:
    cfg = yaml.safe_load(Path(f"{CLONE}/jobs/runs/{JOB}/{codename}.yaml").read_text())
    # The mount path of a Kaggle Model can change, so find the weights by the slug and config.json.
    slug = Path(cfg["model"]["path"]).parts[3]
    weights = min(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts).parent
    cfg["model"]["path"] = str(weights)
    manifest = weights / "manifest.json"
    if manifest.is_file():
        cfg["model"]["revision"] = json.loads(manifest.read_text())["commit"]
    path = Path("/tmp") / f"{codename}.yaml"
    path.write_text(yaml.safe_dump(cfg))
    print(codename, "weights", weights, flush=True)
    return path


end = time.time() + DEADLINE_S
for stage in STAGES:
    processes = []
    for codename, gpu in stage:
        env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
        if gpu is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
        output = Path("/kaggle/working") / codename
        command = [sys.executable, "-m", "src.rl_probe", str(config_file(codename)), "--output", str(output)]
        processes.append((codename, subprocess.Popen(command, cwd=CLONE, env=env)))
    for codename, p in processes:
        try:
            code = p.wait(timeout=max(0.0, end - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            code = "timeout"
        # An error of the kernel deletes all output. Thus a failed process does not stop the job.
        print(codename, "exit code", code, flush=True)
