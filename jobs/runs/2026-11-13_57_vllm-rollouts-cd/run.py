"""Real agent rollouts through a vLLM server, and a check of the vLLM log-probabilities in transformers."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "07-rl-method"
CLONE = "/tmp/repo"
JOB = "2026-11-13_57_vllm-rollouts-cd"
# Each stage runs its codenames at the same time. A GPU of None gives the process both GPUs.
STAGES = [[("vllm-rollouts-d", 0), ("vllm-rollouts-e", 1)], [("vllm-rollouts-f", None)]]
DEADLINE_S = 3 * 3600
ENV = "/tmp/vllm-env"

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
# vLLM brings its own PyTorch, so it gets a separate environment. Both installs run at the same time.
venv = subprocess.Popen(f"uv venv -q --python 3.12 {ENV} && uv pip install -q --python {ENV}/bin/python vllm", shell=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)
# The Kaggle image has torchao 0.10. PEFT 0.21 stops with an ImportError for torchao below 0.16.
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=True)
venv.wait()
print("vllm install exit", venv.returncode, flush=True)
sys.path.insert(0, CLONE)
from src.rl_probe import PATCH_CODE

# The patch is active only with VLLM_TURING_TILE=1. One patch before all servers avoids two writes at the same time.
subprocess.run([f"{ENV}/bin/python", "-c", PATCH_CODE], check=True)

import yaml


def config_file(codename: str) -> Path:
    cfg = yaml.safe_load(Path(f"{CLONE}/jobs/runs/{JOB}/{codename}.yaml").read_text())
    slug = Path(cfg["model"]["path"]).parts[3]
    cfg["model"]["path"] = str(min(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts).parent)
    path = Path("/tmp") / f"{codename}.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


end = time.time() + DEADLINE_S
for stage in STAGES:
    procs = []
    for codename, gpu in stage:
        env = {**os.environ, "VLLM_PYTHON": f"{ENV}/bin/python", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
        if gpu is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
        cmd = [sys.executable, "-m", "src.rl_probe", str(config_file(codename)), "--output", f"/kaggle/working/{codename}"]
        procs.append((codename, subprocess.Popen(cmd, cwd=CLONE, env=env)))
    for codename, p in procs:
        try:
            print(codename, "exit code", p.wait(timeout=max(0.0, end - time.time())), flush=True)
        except subprocess.TimeoutExpired:
            p.kill()
            print(codename, "timeout", flush=True)
    print(json.dumps({"stage": [c for c, _ in stage], "time": time.strftime("%H:%M")}), flush=True)
