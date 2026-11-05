"""Measure the attention kernel of SDPA for Qwen3.5 on a T4 GPU, without and then with flash-linear-attention.

A T4 (sm75) has no flash kernel of SDPA. transformers 5.22.1 calls SDPA with `enable_gqa=True` when the mask is None.
The memory-efficient kernel does not accept GQA, so SDPA uses the math kernel. This kernel keeps a float32 matrix of
heads x length x length. The variant "repeat-kv" copies the key and value heads before SDPA, so the memory-efficient
kernel can run. The variant "repeat-kv" runs only with this kernel, so a silent fallback to the math kernel is not possible.

Each worker does a short warm-up generation first. Thus the times do not include the CUDA start and the Triton compile.
The main process runs one worker for each measurement. A worker is a new process, so the GPU memory is clean.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

SLUGS = {"qwen3.5-2b": "idm-pro-qwen3-5-2b", "qwen3.5-4b": "idm-pro-qwen3-5-4b"}
# Job 09 has the default variant at 2000, 5000 and 10000 tokens. This job repeats 2000 only to compare the tokens.
PLAN_WITHOUT_FLA = [("default", "generate", 2000)]
PLAN_WITHOUT_FLA += [("repeat-kv", "generate", n) for n in (2000, 5000, 10000, 15000, 20000)]
PLAN_WITHOUT_FLA += [("repeat-kv", "backward", n) for n in (2000, 5000, 10000)]
PLAN_WITH_FLA = [("repeat-kv", "generate", n) for n in (2000, 10000, 20000)] + [("repeat-kv", "backward", 5000)]
NEW_TOKENS = 32
OUTPUT = Path("/kaggle/working")


def find_weights(slug: str) -> str:
    configs = sorted(p for p in Path("/kaggle/input").rglob("config.json") if slug in p.parts)
    return str(configs[0].parent)


def worker(path: str, variant: str, mode: str, length: int) -> None:
    import contextlib

    import torch
    import transformers
    import transformers.integrations.sdpa_attention as sdpa
    from torch.nn.attention import SDPBackend, sdpa_kernel
    from transformers.utils import is_flash_linear_attention_available

    result = {"variant": variant, "mode": mode, "length": length, "fla": is_flash_linear_attention_available()}
    kernel = contextlib.nullcontext()
    if variant == "repeat-kv":
        sdpa.use_gqa_in_sdpa = lambda *args, **kwargs: False
        kernel = sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])
    try:
        tok = transformers.AutoTokenizer.from_pretrained(path)
        model = transformers.AutoModelForCausalLM.from_pretrained(path, dtype=torch.float16).to("cuda").eval()
        text = "Zmień priorytet zgłoszenia na najwyższy i przypisz je do Ewy Mazur. " * (length // 8 + 10)
        ids = tok(text, return_tensors="pt").input_ids[:, :length].to("cuda")
        result["weights_gb"] = round(torch.cuda.memory_allocated() / 1e9, 2)
        with kernel:
            start = time.time()
            with torch.no_grad():
                model.generate(ids[:, :300], max_new_tokens=2, min_new_tokens=2, do_sample=False)
            torch.cuda.synchronize()
            result["warmup_s"] = round(time.time() - start, 2)
            if mode == "generate":
                timings = {}
                for name, new in (("prefill", 1), ("total", NEW_TOKENS + 1)):
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
                    start = time.time()
                    with torch.no_grad():
                        out = model.generate(ids, max_new_tokens=new, min_new_tokens=new, do_sample=False)
                    torch.cuda.synchronize()
                    timings[name] = round(time.time() - start, 2)
                    result[f"peak_gb_{name}"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
                result.update(prefill_s=timings["prefill"], decode_s=round(timings["total"] - timings["prefill"], 2))
                result["tokens"] = out[0, length:].tolist()
            else:
                # The weights stay frozen. The gradient goes to the input embeddings through all layers,
                # as for LoRA. The model calculates the activations again in the backward pass, so they use less memory.
                model.requires_grad_(False)
                model.gradient_checkpointing_enable()
                model.train()
                embeds = model.get_input_embeddings()(ids).detach().requires_grad_(True)
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                start = time.time()
                logits = model(inputs_embeds=embeds, logits_to_keep=1).logits
                logits.float().logsumexp(-1).sum().backward()
                torch.cuda.synchronize()
                result.update(backward_s=round(time.time() - start, 2),
                              peak_gb_backward=round(torch.cuda.max_memory_allocated() / 1e9, 2))
    except Exception as e:  # noqa: BLE001  An OOM is a result of the measurement.
        result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    print("RESULT", json.dumps(result), flush=True)


def measure(label: str, plan: list[tuple]) -> list[dict]:
    rows = []
    for model, slug in SLUGS.items():
        path = find_weights(slug)
        for variant, mode, length in plan:
            done = subprocess.run([sys.executable, __file__, "worker", path, variant, mode, str(length)],
                                  capture_output=True, text=True)
            line = next((ln for ln in done.stdout.splitlines() if ln.startswith("RESULT ")), None)
            row = json.loads(line[7:]) if line else {"variant": variant, "mode": mode, "length": length,
                                                      "error": done.stderr[-300:]}
            row.update(setup=label, model=model)
            print(json.dumps({k: v for k, v in row.items() if k != "tokens"}), flush=True)
            rows.append(row)
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
        sys.exit(0)
    # The same version of transformers as in requirements-kaggle.txt.
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "transformers==5.22.1"], check=True)
    import torch

    print("gpu", torch.cuda.get_device_name(0), "torch", torch.__version__, flush=True)
    rows = measure("without fla", PLAN_WITHOUT_FLA)
    (OUTPUT / "bench.json").write_text(json.dumps(rows, indent=2) + "\n")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-warn-conflicts", "flash-linear-attention==0.6.0"],
                   check=True)
    rows += measure("with fla", PLAN_WITH_FLA)
    (OUTPUT / "bench.json").write_text(json.dumps(rows, indent=2) + "\n")
    # The greedy search gives the same tokens if the kernels give the same logits.
    for model in SLUGS:
        tokens = {f"{r['setup']}/{r['variant']}": r["tokens"] for r in rows
                  if r["model"] == model and r["length"] == 2000 and "tokens" in r}
        reference = tokens.get("without fla/default")
        print(json.dumps({"model": model, "same_tokens_as_default": {k: v == reference for k, v in tokens.items()}}),
              flush=True)
