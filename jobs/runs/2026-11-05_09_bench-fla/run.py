"""Measure the time and the GPU memory of Qwen3.5 with and without flash-linear-attention.

The main process runs one worker for each model and prompt length. A worker is a new process, so the GPU memory is clean.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

SLUGS = {"qwen3.5-2b": "idm-pro-qwen3-5-2b", "qwen3.5-4b": "idm-pro-qwen3-5-4b"}
LENGTHS = [2000, 5000, 10000]
NEW_TOKENS = 32
OUTPUT = Path("/kaggle/working")


def find_weights(slug: str) -> str:
    configs = sorted(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts)
    return str(configs[0].parent)


def worker(path: str, length: int) -> None:
    import torch
    import transformers
    from transformers.utils import is_flash_linear_attention_available

    result = {"path": path, "length": length, "fla": is_flash_linear_attention_available()}
    try:
        tok = transformers.AutoTokenizer.from_pretrained(path)
        model = transformers.AutoModelForCausalLM.from_pretrained(path, dtype=torch.float16).to("cuda").eval()
        text = "Zmień priorytet zgłoszenia na najwyższy i przypisz je do Ewy Mazur. " * (length // 8 + 10)
        ids = tok(text, return_tensors="pt").input_ids[:, :length].to("cuda")
        timings = {}
        for name, new in (("prefill", 1), ("total", NEW_TOKENS + 1)):
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            start = time.time()
            with torch.no_grad():
                model.generate(ids, max_new_tokens=new, min_new_tokens=new, do_sample=False)
            torch.cuda.synchronize()
            timings[name] = round(time.time() - start, 2)
            result[f"peak_gb_{name}"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        result.update(prefill_s=timings["prefill"], decode_s=round(timings["total"] - timings["prefill"], 2))
    except Exception as e:  # noqa: BLE001  An OOM is a result of the measurement.
        result["error"] = f"{type(e).__name__}: {str(e)[:150]}"
    print("RESULT", json.dumps(result), flush=True)


def measure(label: str) -> list[dict]:
    rows = []
    for model, slug in SLUGS.items():
        path = find_weights(slug)
        for length in LENGTHS:
            done = subprocess.run([sys.executable, __file__, "worker", path, str(length)], capture_output=True, text=True)
            line = next((ln for ln in done.stdout.splitlines() if ln.startswith("RESULT ")), None)
            row = json.loads(line[7:]) if line else {"error": done.stderr[-200:]}
            row.update(setup=label, model=model)
            print(json.dumps(row), flush=True)
            rows.append(row)
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(sys.argv[2], int(sys.argv[3]))
        sys.exit(0)
    # The same version of transformers as in requirements-kaggle.txt.
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "transformers==5.22.1"], check=True)
    import torch

    print("gpu", torch.cuda.get_device_name(0), "torch", torch.__version__, flush=True)
    rows = measure("without fla")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "flash-linear-attention"], check=True)
    rows += measure("with fla")
    (OUTPUT / "bench.json").write_text(json.dumps(rows, indent=2) + "\n")
