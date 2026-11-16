"""Acceptance of the RL code: Gemma 4 E2B, the memory check of Gemma 4 E4B with 12288 tokens (must stop the run), Gemma 4 E4B."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "41-e3-rl-code"
CLONE = "/tmp/repo"
JOB = "2026-11-16_79_rl-accept-def"
# Each stage is one command: an RL run ("train", optionally with "resume") or an evaluation ("evaluate").
STAGES = [{"codename": "rl-accept-d", "kind": "train", "vllm": False}, {"codename": "rl-accept-e", "kind": "train", "vllm": False}, {"codename": "rl-accept-f", "kind": "train", "vllm": False}]
VLLM = "vllm==0.33.0"  # The version of jobs 51 to 61.
ENV = "/tmp/vllm-env"
DEADLINE_S = int(2.5 * 3600)


def find_output(rel: str) -> Path:
    """A folder of an earlier stage: first in this job, then in the output of an earlier job (kernel source)."""
    local = Path("/kaggle/working") / rel
    if local.exists():
        return local
    head = rel.split("/")[0]
    found = sorted(p for p in Path("/kaggle/input").rglob(head) if p.is_dir() and (p / rel[len(head):].lstrip("/")).exists())
    if not found:
        raise FileNotFoundError(f"no folder {rel} in /kaggle/working or /kaggle/input")
    return found[0] / rel[len(head):].lstrip("/")


def config_file(codename: str) -> Path:
    import yaml

    cfg = yaml.safe_load(Path(f"{CLONE}/jobs/runs/{JOB}/{codename}.yaml").read_text())
    slug = Path(cfg["model"]["path"]).parts[3]
    cfg["model"]["path"] = str(min(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts).parent)
    cfg["model"]["adapters"] = [str(find_output(a.removeprefix("output:"))) if a.startswith("output:") else a
                                for a in cfg["model"].get("adapters") or []]
    if not cfg["model"]["adapters"]:
        cfg["model"].pop("adapters")
    path = Path("/tmp") / f"{codename}.yaml"
    path.write_text(yaml.safe_dump(cfg))
    print(codename, json.dumps(cfg), flush=True)
    return path


def main() -> None:
    subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
    print("commit", subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], check=True, capture_output=True,
                                   text=True).stdout.strip(), flush=True)
    import torch

    print("torch", torch.__version__, "gpus", torch.cuda.device_count(), flush=True)
    need_vllm = any(s.get("vllm") for s in STAGES)
    venv = None
    if need_vllm:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
        # vLLM brings its own PyTorch, so it gets a separate environment. Both installs run at the same time.
        venv = subprocess.Popen(f"uv venv -q --python 3.12 {ENV} && uv pip install -q --python {ENV}/bin/python {VLLM}",
                                shell=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "-r",
                    f"{CLONE}/requirements-kaggle.txt"], check=True)
    # The Kaggle image has torchao 0.10. PEFT 0.21 stops with an ImportError for torchao below 0.16.
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=True)
    if venv is not None:
        venv.wait()
        print("vllm install exit", venv.returncode, flush=True)
    end = time.time() + DEADLINE_S
    for stage in STAGES:
        codename = stage["codename"]
        env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True", "PYTHONUNBUFFERED": "1"}
        if need_vllm:
            env["VLLM_PYTHON"] = f"{ENV}/bin/python"
        out = f"/kaggle/working/{codename}"
        try:
            if stage["kind"] == "train":
                cmd = [sys.executable, "-m", "src.rl.train", str(config_file(codename)), "--output", out]
                if stage.get("resume"):
                    cmd += ["--resume", str(find_output(stage["resume"]))]
            else:
                cmd = [sys.executable, "-m", "src.evaluate", str(config_file(codename)), "--output", out]
        except Exception as e:  # noqa: BLE001  A missing input must not delete the output of the earlier stages.
            print(codename, "setup failed:", e, flush=True)
            continue
        start = time.time()
        proc = subprocess.Popen(cmd, cwd=CLONE, env=env)
        try:
            code = proc.wait(timeout=max(60.0, end - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()
            code = "timeout"
        status = Path(out) / "status.json"
        print(json.dumps({"stage": codename, "exit": code, "time_s": round(time.time() - start),
                          "status": json.loads(status.read_text()) if status.exists() else None}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001  Kaggle deletes the output of a failed kernel.
        print("job failed:", repr(e), flush=True)
