"""Short vLLM speed probe: one model on each GPU, at most 17 minutes."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "07-rl-method"
CLONE = "/tmp/repo"
JOB = "2026-11-12_53_vllm-probe-cd"
# codename, family, weights slug, GPU, Turing patch
MODELS = [("vllm-probe-c", "bielik", "idm-pro-bielik-1-5b-v3", 0, False), ("vllm-probe-d", "qwen3.5", "idm-pro-qwen3-5-4b", 1, False)]
END = time.time() + 17 * 60
OUT = Path("/kaggle/working")
ENV = "/tmp/vllm-env"

subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(), flush=True)
# Both installs run at the same time to save minutes.
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
venv = subprocess.Popen(f"uv venv -q --python 3.12 {ENV} && uv pip install -q --python {ENV}/bin/python vllm", shell=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "-r", f"{CLONE}/requirements-kaggle.txt"], check=True)
sys.path.insert(0, CLONE)

import asyncio

import transformers

from src.environment import load_board
from src.models import get_family, load_prompt
from src.rl_probe import _list_tools, select_tasks
from src.tasks import board_path
from src.tools import build_server

task = select_tasks("test", 1, 0)[0]
tools = asyncio.run(_list_tools(build_server(load_board(board_path(task.board)))))
messages = [{"role": "system", "content": load_prompt("system", "v3").text}, {"role": "user", "content": task.instruction}]
jobs = []
for codename, family, slug, gpu, patch in MODELS:
    weights = min(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts).parent
    tok = transformers.AutoTokenizer.from_pretrained(weights, local_files_only=True)
    text = get_family(family).render(tok, messages, tools, False)
    ids = tok(text, add_special_tokens=False)["input_ids"]
    (OUT / codename).mkdir(exist_ok=True)
    Path(f"/tmp/{codename}-ids.json").write_text(json.dumps(ids))
    jobs.append((codename, weights, gpu, patch))
    print(codename, "prompt tokens", len(ids), flush=True)
venv.wait()
print("vllm install exit", venv.returncode, flush=True)
procs = []
for codename, weights, gpu, patch in jobs:
    cmd = [f"{ENV}/bin/python", f"{CLONE}/jobs/runs/{JOB}/vllm_bench.py", "--model", str(weights),
           "--ids", f"/tmp/{codename}-ids.json", "--out", str(OUT / codename / "vllm.json")]
    if patch:
        cmd.append("--turing-patch")
    procs.append((codename, subprocess.Popen(cmd, env={**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu)})))
for (codename, p), (_, _, gpu, _) in zip(procs, jobs):
    try:
        print(codename, "exit", p.wait(timeout=max(0, END - time.time())), flush=True)
    except subprocess.TimeoutExpired:
        p.kill()
        print(codename, "timeout", flush=True)
        continue
    result = OUT / codename / "vllm.json"
    if result.exists() and "batches" not in json.loads(result.read_text()) and time.time() < END - 120:
        # A failed load keeps GPU memory in its process. Thus the eager try starts a new process.
        result.rename(result.with_name("vllm-graphs.json"))
        cmd = [arg for arg in p.args] + ["--eager"]
        retry = subprocess.Popen(cmd, env={**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu)})
        try:
            print(codename, "eager exit", retry.wait(timeout=max(0, END - time.time())), flush=True)
        except subprocess.TimeoutExpired:
            retry.kill()
            print(codename, "eager timeout", flush=True)
