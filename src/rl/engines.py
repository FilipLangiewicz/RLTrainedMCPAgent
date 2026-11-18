"""Generation engines and the model object for one rollout (design Decisions 3 and 5).

Each engine has the same interface: `start()`, `model_for_rollout(lane, temperature)`, `load_adapter(path)`,
`stop()` and the number of `lanes` (rollouts at the same time).
"""

import json
import os
import signal
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from src.models import Model, ModelOutput
from src.rl.tokens import Turn


class ContextLimit(RuntimeError):
    """The prompt of a turn is longer than rl.max_context_tokens."""


class Cancelled(RuntimeError):
    """The run stops, so the rollout stops before its next turn."""


class RolloutModel(Model):
    """The interface of the model layer for the agent loop. It records the exact tokens of each turn."""

    backend = "rl"

    def __init__(self, engine, lane: int, temperature: float):
        super().__init__(engine.family, engine.path, None, engine.thinking)
        self.engine, self.lane, self.temperature = engine, lane, temperature
        self.turns: list[Turn] = []
        self.context_limit = False
        self.engine_error: str | None = None

    def generate(self, messages, tools):
        if self.engine.cancel.is_set():
            raise Cancelled("the run stops")
        self.steps += 1
        tok = self.engine.tokenizer
        prompt = self.family.render(tok, messages, tools, self.thinking)
        ids = tok(prompt, add_special_tokens=False)["input_ids"]
        # The output must also fit, so that each turn fits in one sample of the backward pass.
        room = min(self.engine.max_new_tokens, self.engine.max_context_tokens - len(ids))
        if room < min(16, self.engine.max_new_tokens):
            self.context_limit = True
            raise ContextLimit(f"{len(ids)} prompt tokens, limit {self.engine.max_context_tokens}")
        try:
            output, logprobs = self.engine.sample(self.lane, ids, room, self.temperature)
        except Exception as e:
            self.engine_error = f"{type(e).__name__}: {str(e)[:300]}"
            raise
        self.turns.append(Turn(prompt=ids, output=output, logprobs=logprobs))
        text = tok.decode(output, skip_special_tokens=False)
        for token in {tok.eos_token, tok.pad_token, tok.bos_token} - {None}:
            text = text.replace(token, "")
        content, calls, thinking = self.family.parse(self.family.clean(text), tools, self.steps)
        return ModelOutput(text=content, calls=calls, thinking_text=thinking, input_tokens=len(ids),
                           output_tokens=len(output))


class Engine:
    lanes = 1

    def __init__(self, cfg: dict, tokenizer):
        from src.models import get_family

        model, rl = cfg["model"], cfg["rl"]
        self.cfg, self.tokenizer = cfg, tokenizer
        self.family, self.path, self.thinking = get_family(model["family"]), model["path"], model["thinking"]
        self.max_new_tokens, self.max_context_tokens = model["max_new_tokens"], rl["max_context_tokens"]
        self.temperature = rl["temperature"]
        self.cancel = threading.Event()

    def model_for_rollout(self, lane: int, temperature: float | None = None) -> RolloutModel:
        return RolloutModel(self, lane, self.temperature if temperature is None else temperature)

    def sample(self, lane: int, prompt: list[int], max_new: int, temperature: float) -> tuple[list[int], list[float]]:
        raise NotImplementedError

    def start(self) -> None:
        pass

    def load_adapter(self, path: str | Path) -> None:
        pass

    def stop(self) -> None:
        pass

    def describe(self) -> dict:
        return {}


# vLLM

# The code runs in the vLLM environment. It wraps _get_tile_size: a tile of 16 fits the 64 KB of shared memory of a T4.
PATCH_LINES = [
    "import importlib.util, pathlib",
    "root = pathlib.Path(importlib.util.find_spec('vllm').origin).parent",
    "wrapper = '\\n'.join(['', 'def _get_tile_size(*args, **kwargs):',",
    "    '    import os as _os', '    import torch as _torch', '    size = _get_tile_size_orig(*args, **kwargs)',",
    "    '    if _os.environ.get(\"VLLM_TURING_TILE\") == \"1\" and _torch.cuda.get_device_capability()[0] < 8:',",
    "    '        return min(size, 16)', '    return size', ''])",
    "for path in root.rglob('*.py'):",
    "    text = path.read_text(errors='ignore')",
    "    if 'def _get_tile_size(' in text and '_get_tile_size_orig' not in text:",
    "        path.write_text(text.replace('def _get_tile_size(', 'def _get_tile_size_orig(') + wrapper)",
    "        print('patched', path)",
]
PATCH_CODE = "\n".join(PATCH_LINES)


def post_json(url: str, body: dict, timeout: float = 600) -> str:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(errors="ignore")


class VllmEngine(Engine):
    """`vllm serve` from a separate environment on GPU 0. The server gets each new LoRA adapter without a restart."""

    def __init__(self, cfg: dict, tokenizer, served_path: str, gpu: int = 0):
        super().__init__(cfg, tokenizer)
        self.engine_cfg, self.served_path, self.gpu = cfg["engine"], served_path, gpu
        self.lanes = self.engine_cfg["concurrency"]
        self.proc, self.client, self.served, self.start_s = None, None, "m", None
        self.top_k = 0

    def _command(self) -> tuple[list[str], dict]:
        e, rl = self.engine_cfg, self.cfg["rl"]
        python = os.environ.get("VLLM_PYTHON")
        if not python:
            raise RuntimeError("the engine vllm needs VLLM_PYTHON, the Python of the vLLM environment")
        config = json.loads((Path(self.served_path) / "config.json").read_text())
        limit = config.get("text_config", config).get("max_position_embeddings") or self.max_context_tokens
        self.max_context_tokens = min(self.max_context_tokens, limit)
        cmd = [python, "-m", "vllm.entrypoints.openai.api_server", "--model", self.served_path,
               "--served-model-name", "m", "--dtype", "float16", "--max-model-len", str(self.max_context_tokens),
               "--port", str(e["port"]), "--gpu-memory-utilization", str(e["gpu_memory"]), "--enable-prefix-caching",
               "--max-num-seqs", str(e["max_seqs"]),
               "--compilation-config", json.dumps({"cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32, 64]})]
        if self.cfg["rl"]["mode"] == "train":
            cmd += ["--enable-lora", "--max-lora-rank", str(rl["lora_rank"]), "--max-loras", "2"]
        if e["batched_tokens"]:
            # A smaller prefill chunk needs less activation memory. Then the KV cache of a 4B model fits on a T4.
            cmd += ["--max-num-batched-tokens", str(e["batched_tokens"])]
        if self.temperature != 1.0:
            # The ratio of GRPO needs the log-probabilities after the temperature.
            cmd += ["--logprobs-mode", "processed_logprobs"]
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(self.gpu), "VLLM_TURING_TILE": "1" if e["patch"] else "0",
               "VLLM_ALLOW_RUNTIME_LORA_UPDATING": "True"}
        return cmd, env

    def start(self) -> None:
        from openai import OpenAI

        cmd, env = self._command()
        if self.engine_cfg["patch"]:
            subprocess.run([cmd[0], "-c", PATCH_CODE], check=True)
        start = time.perf_counter()
        # A new session gives the server and its engine processes one process group, so that one signal stops them all.
        self.proc = subprocess.Popen(cmd, env=env, start_new_session=True)
        self.url = f"http://127.0.0.1:{self.engine_cfg['port']}"
        while time.perf_counter() - start < 60 * self.engine_cfg["start_minutes"]:
            if self.proc.poll() is not None:
                raise RuntimeError(f"vllm serve stopped with code {self.proc.returncode}")
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                    if r.status == 200:
                        self.start_s = round(time.perf_counter() - start, 1)
                        self.client = OpenAI(base_url=self.url + "/v1", api_key="none", max_retries=2, timeout=900)
                        return
            except OSError:
                pass
            time.sleep(5)
        self.stop()
        raise TimeoutError("vllm serve did not start in time")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _complete(self, prompt, max_new, temperature):
        extra = {"top_k": self.top_k, "skip_special_tokens": False, "return_tokens_as_token_ids": True}
        return self.client.completions.create(model=self.served, prompt=prompt, max_tokens=max_new,
                                              temperature=temperature, top_p=1.0, logprobs=1, extra_body=extra)

    def sample(self, lane, prompt, max_new, temperature):
        if not self.alive():
            raise RuntimeError("the vLLM server does not run")
        try:
            response = self._complete(prompt, max_new, temperature)
        except Exception as e:  # Some vLLM versions accept only -1 to disable top-k.
            if "top_k" not in str(e) or self.top_k == -1:
                raise
            self.top_k = -1
            response = self._complete(prompt, max_new, temperature)
        lp = response.choices[0].logprobs
        tokens = [int(t.split(":")[-1]) for t in lp.tokens]
        return tokens, [float(x) if x is not None else 0.0 for x in lp.token_logprobs]

    def load_adapter(self, path) -> None:
        name = f"a{int(time.time() * 1000)}"
        post_json(self.url + "/v1/load_lora_adapter", {"lora_name": name, "lora_path": str(path)})
        old, self.served = self.served, name
        if old != "m":
            post_json(self.url + "/v1/unload_lora_adapter", {"lora_name": old})

    def stop(self) -> None:
        if self.proc is None:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
                self.proc.wait(timeout=90)
                break
            except ProcessLookupError:
                break
            except subprocess.TimeoutExpired:
                continue
        self.proc = None

    def describe(self) -> dict:
        return {"vllm_start_s": self.start_s, "served_path": self.served_path,
                "max_context_tokens": self.max_context_tokens}


# transformers

class TransformersEngine(Engine):
    """One model copy on each GPU. Each copy samples one rollout after the other in its own lane."""

    def __init__(self, cfg: dict, policies: list):
        super().__init__(cfg, policies[0].tokenizer)
        self.policies = policies
        self.lanes = len(policies)

    def sample(self, lane, prompt, max_new, temperature):
        policy = self.policies[lane % len(self.policies)]
        torch = policy.torch
        if torch.cuda.is_available() and str(policy.device).startswith("cuda"):
            torch.cuda.set_device(torch.device(policy.device))
        try:
            return policy.sample(prompt, max_new, temperature)
        except torch.cuda.OutOfMemoryError:
            policy.free_memory()
            raise
