"""Measure the speed of sampled generation in vLLM for one model. It runs in a separate virtual environment with vLLM.

Usage: python vllm_bench.py --model <folder> --ids <prompt ids json> --out <result json> [--tp 2] [--turing-patch]
"""
import argparse
import json
import os
import time
import traceback
from pathlib import Path

# The engine runs in this process. Thus the patch below also applies to the engine.
os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")

WRAPPER = '''

def _get_tile_size(*args, **kwargs):
    import os as _os
    import torch as _torch
    size = _get_tile_size_orig(*args, **kwargs)
    # A T4 has 64 KB of shared memory. A tile of 16 keeps the head size 512 of Gemma 4 inside this limit.
    if _os.environ.get("VLLM_TURING_TILE") == "1" and _torch.cuda.get_device_capability()[0] < 8:
        return min(size, 16)
    return size
'''


def patch_tile_size() -> list[str]:
    """Wrap _get_tile_size of vLLM in its source files. The wrapper is active only with VLLM_TURING_TILE=1."""
    import importlib.util

    root = Path(importlib.util.find_spec("vllm").origin).parent
    done = []
    for path in root.rglob("*.py"):
        text = path.read_text(errors="ignore")
        if "def _get_tile_size(" in text and "_get_tile_size_orig" not in text:
            path.write_text(text.replace("def _get_tile_size(", "def _get_tile_size_orig(") + WRAPPER)
            done.append(str(path.relative_to(root)))
    return done


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--ids", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tp", type=int, default=1)
    p.add_argument("--max-len", type=int, default=16384)
    p.add_argument("--turing-patch", action="store_true")
    args = p.parse_args()
    result = {"model": args.model, "tp": args.tp}
    out = Path(args.out)

    def save():
        out.write_text(json.dumps(result, indent=2))

    result["patched"] = patch_tile_size()
    if args.turing_patch:
        os.environ["VLLM_TURING_TILE"] = "1"
    import vllm
    from vllm import LLM, SamplingParams

    result["vllm"] = vllm.__version__
    ids = json.loads(Path(args.ids).read_text())
    result["prompt_tokens"] = len(ids)
    config = json.loads((Path(args.model) / "config.json").read_text())
    limit = config.get("text_config", config).get("max_position_embeddings") or args.max_len
    args.max_len = min(args.max_len, limit)  # Bielik 1.5B accepts only 8192 tokens.
    result["max_len"] = args.max_len
    llm = None
    for eager in (False, True):
        start = time.perf_counter()
        try:
            llm = LLM(model=args.model, dtype="float16", tensor_parallel_size=args.tp, max_model_len=args.max_len,
                      gpu_memory_utilization=0.88, enable_prefix_caching=True, seed=0, enforce_eager=eager,
                      generation_config="vllm")
            result["eager"], result["load_s"] = eager, round(time.perf_counter() - start, 1)
            break
        except Exception:  # noqa: BLE001  The second try uses eager mode without CUDA graphs.
            result[f"load_error_eager_{eager}"] = traceback.format_exc(limit=4)[-3000:]
            save()
    if llm is None:
        save()
        return

    def params(seed, **extra):
        return SamplingParams(temperature=1.0, top_p=1.0, max_tokens=128, min_tokens=128, seed=seed, **extra)

    prompt = {"prompt_token_ids": ids}
    llm.generate([prompt], params(0), use_tqdm=False)  # The first call compiles kernels, so it does not count.
    rows = []
    for n in (1, 8, 16, 32, 64):
        start = time.perf_counter()
        try:
            outs = llm.generate([prompt] * n, [params(1000 + i) for i in range(n)], use_tqdm=False)
            seconds = time.perf_counter() - start
            tokens = sum(len(o.outputs[0].token_ids) for o in outs)
            rows.append({"parallel": n, "time_s": round(seconds, 2), "tokens": tokens, "tokens_per_s": round(tokens / seconds, 1)})
        except Exception:  # noqa: BLE001
            rows.append({"parallel": n, "error": traceback.format_exc(limit=2)[-800:]})
        print("vllm", rows[-1], flush=True)
        result["batches"] = rows
        save()
    sample = llm.generate([prompt], params(7, logprobs=0), use_tqdm=False)[0].outputs[0]
    result["sample_ids"] = list(sample.token_ids)
    result["sample_logprobs"] = [lp[t].logprob for t, lp in zip(sample.token_ids, sample.logprobs)]
    save()


if __name__ == "__main__":
    main()
