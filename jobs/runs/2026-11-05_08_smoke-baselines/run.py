"""Smoke test of the six baseline models: four test tasks for each model, one model after another.

A failed model does not stop the job, because a failed kernel loses its complete output.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "06-e1-baselines"
CLONE = "/tmp/repo"  # Not in the output folder, so the clone is not an output.
JOB = "2026-11-05_08_smoke-baselines"
CODENAMES = ["smoke-qwen3-5-2b", "smoke-qwen3-5-4b", "smoke-bielik-1-5b-v3", "smoke-bielik-4-5b-v3",
             "smoke-gemma-4-e2b", "smoke-gemma-4-e4b"]
OUTPUT = Path("/kaggle/working")

import torch

assert torch.cuda.device_count() == 2, "this job needs 2 GPUs (T4 x2): check the phone verification of the account"
print("torch", torch.__version__, "cuda", torch.version.cuda, flush=True)

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)

import yaml

status = {}
for codename in CODENAMES:
    cfg = yaml.safe_load(Path(f"{CLONE}/jobs/runs/{JOB}/{codename}.yaml").read_text())
    # The folder inside the Kaggle Model can change, so find the weights by config.json.
    configs = sorted(Path(cfg["model"]["path"]).rglob("config.json"))
    if not configs:
        status[codename] = "no weights"
        print(codename, "no weights under", cfg["model"]["path"], flush=True)
        continue
    weights = configs[0].parent
    cfg["model"]["path"] = str(weights)
    manifest = weights / "manifest.json"
    if manifest.is_file():
        cfg["model"]["revision"] = json.loads(manifest.read_text())["commit"]
    resolved = Path("/tmp") / f"{codename}.yaml"
    resolved.write_text(yaml.safe_dump(cfg))
    start = time.time()
    done = subprocess.run([sys.executable, "-m", "src.evaluate", str(resolved), "--output", str(OUTPUT / codename)], cwd=CLONE)
    status[codename] = f"exit {done.returncode}, {time.time() - start:.0f} s"
    print(codename, status[codename], flush=True)
    torch.cuda.empty_cache()

(OUTPUT / "status.json").write_text(json.dumps(status, indent=2) + "\n")
print(json.dumps(status, indent=2), flush=True)
