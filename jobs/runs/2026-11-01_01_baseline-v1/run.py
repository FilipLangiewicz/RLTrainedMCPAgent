"""Run the baseline evaluation (Qwen3-1.7B with the prompt only) on the test set. Each GPU runs one half of the tasks."""
import os
import subprocess
import sys
import time

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "main"
CLONE = "/tmp/repo"  # Not in the output folder, so the clone is not an output.
CODENAME = "baseline-v1"
OUTPUT = f"/kaggle/working/{CODENAME}"
GPUS = 2
DEADLINE_S = 10.5 * 3600  # Stop the shards before the 12-hour limit of the session.

import torch

# A long job on the CPU wastes hours, so stop immediately without the GPUs.
assert torch.cuda.device_count() == GPUS, "this job needs 2 GPUs (T4 x2): check the phone verification of the account"
print("torch", torch.__version__, "cuda", torch.version.cuda, flush=True)

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)

# One process for each GPU. Each process sees only its GPU as "cuda".
shards = [f"{OUTPUT}/shards/{i}" for i in range(GPUS)]
processes = [
    subprocess.Popen([sys.executable, "-m", "src.evaluate", CODENAME, "--output", shards[i], "--shard", f"{i}/{GPUS}"],
                     cwd=CLONE, env={**os.environ, "CUDA_VISIBLE_DEVICES": str(i)})
    for i in range(GPUS)
]
end = time.time() + DEADLINE_S
codes = []
for p in processes:
    try:
        codes.append(p.wait(timeout=max(0.0, end - time.time())))
    except subprocess.TimeoutExpired:
        p.kill()
        codes.append("timeout")
print("shard exit codes", codes, flush=True)

# An error of the kernel deletes all output. Thus a failed shard does not stop the job, and the other shard stays.
if all(code == 0 for code in codes):
    subprocess.run([sys.executable, "-m", "src.evaluate", "--merge", *shards, "--output", OUTPUT], cwd=CLONE, check=True)
else:
    print("FAILED: not all shards are complete. The results of each shard are in", f"{OUTPUT}/shards", flush=True)
