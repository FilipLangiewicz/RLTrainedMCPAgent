"""The trainer model: fp16 base weights, the merged start adapters and a new LoRA adapter (design Decisions 7 and 8)."""

import contextlib
import gc
import json
from pathlib import Path

from src.models import (
    avoid_gqa_in_sdpa,
    get_family,
    load_weights,
    merge_adapters,
    model_fingerprint,
)
from src.rl.grpo import token_logprobs

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
# vLLM and the RL code do not train the vision and audio parts.
LORA_EXCLUDE = r".*(vision|audio|visual).*"


def lora_config(rl: dict):
    from peft import LoraConfig

    return LoraConfig(r=rl["lora_rank"], lora_alpha=rl["lora_alpha"], lora_dropout=rl["lora_dropout"],
                      target_modules=LORA_TARGETS, exclude_modules=LORA_EXCLUDE, task_type="CAUSAL_LM")


def ple_tables(model, torch) -> dict:
    return {n: m for n, m in model.named_modules() if isinstance(m, torch.nn.Embedding) and "per_layer" in n}


def move_weights(model, device: str, keep: set) -> None:
    """Move all weights except the tensors in `keep`. Each tensor moves on its own, so that Gemma 4 E4B fits."""
    import torch

    for t in [*model.parameters(), *model.buffers()]:
        if id(t) not in keep:
            t.data = t.data.to(device)
            if getattr(t, "grad", None) is not None:
                t.grad = t.grad.to(device)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def offload_tables(model, device: str, shared: dict | None = None) -> set:
    """Keep the per-layer lookup tables (PLE) of Gemma 4 in CPU memory and put all other weights on the GPU.

    A lookup needs no matrix product, so the CPU gives the rows quickly. With `shared`, the model uses the tables
    of another copy, and the RAM keeps only one table.
    """
    import torch

    tables = ple_tables(model, torch)
    if shared:
        for name, module in tables.items():
            module.weight = shared[name].weight
    keep = {id(t) for m in tables.values() for t in [*m.parameters(), *m.buffers()]}
    move_weights(model, device, keep)
    for m in tables.values():
        m.register_forward_pre_hook(lambda mod, args: tuple(a.to("cpu") if torch.is_tensor(a) else a for a in args))
        m.register_forward_hook(lambda mod, args, out: out.to(device))
    return keep


class _Capture:
    """Takes the place of the output layer. It keeps the hidden states and gives small dummy logits."""

    def __init__(self, torch):
        self.module = torch.nn.Module()
        self.module.forward = self.forward
        self.hidden = None

    def forward(self, x):
        self.hidden = x
        return x.new_zeros(*x.shape[:-1], 1)


class _Recorder:
    """A logits processor that records the log-probability of each sampled token without a copy of all logits."""

    def __init__(self, torch, temperature: float):
        self.torch, self.temperature, self.previous, self.logprobs = torch, temperature, None, []

    def __call__(self, input_ids, scores):
        if self.previous is not None:
            self.logprobs.append(self.previous[input_ids[0, -1]])
        if self.temperature > 0:
            # The temperature applies here, and generate gets 1.0. Thus the record and the sampler agree.
            scores = scores / self.temperature
        self.previous = self.torch.log_softmax(scores[0].float(), -1)
        return scores

    def finish(self, last_token: int) -> list[float]:
        values = [*self.logprobs, self.previous[last_token]] if self.previous is not None else []
        return self.torch.stack(values).tolist() if values else []


class Policy:
    def __init__(self, model_cfg: dict, rl: dict, device: str, train: bool = True, shared_tables: dict | None = None,
                 save_merged_to: str | None = None):
        import torch

        self.torch, self.device, self.rl = torch, device, rl
        self.path, self.family = model_cfg["path"], get_family(model_cfg["family"])
        self.thinking = model_cfg["thinking"]
        avoid_gqa_in_sdpa()
        self.tokenizer, model = load_weights(model_cfg["path"], model_cfg.get("revision"), model_cfg["dtype"])
        self.offload = self.family.name == "gemma4"
        if self.offload:
            offload_tables(model, device, shared_tables)
        else:
            model.to(device)
        model = merge_adapters(model, model_cfg.get("adapters") or [])
        self.base = model
        if save_merged_to:
            self.save_merged(save_merged_to)
        text = model.config.get_text_config() if hasattr(model.config, "get_text_config") else model.config
        self.softcap = getattr(text, "final_logit_softcapping", None) or 0.0
        self.model = model
        self.lora = train
        if train:
            from peft import get_peft_model

            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
            model.enable_input_require_grads()
            self.model = get_peft_model(model, lora_config(rl))
        self.model.eval()

    # Weights

    def tables(self) -> dict:
        return ple_tables(self.base, self.torch)

    def parameters(self) -> list:
        return [p for p in self.model.parameters() if p.requires_grad]

    def named_lora(self) -> dict:
        return {n: p for n, p in self.model.named_parameters() if p.requires_grad}

    def lora_state(self) -> dict:
        from peft import get_peft_model_state_dict

        return get_peft_model_state_dict(self.model)

    def load_lora_state(self, state: dict) -> None:
        from peft import set_peft_model_state_dict

        set_peft_model_state_dict(self.model, state)

    def load_adapter_folder(self, folder: str | Path) -> None:
        from safetensors.torch import load_file

        self.load_lora_state(load_file(str(Path(folder) / "adapter_model.safetensors")))

    def save_adapter(self, folder: str | Path) -> None:
        folder = Path(folder)
        self.model.save_pretrained(folder)
        (folder / "base_model.json").write_text(json.dumps(model_fingerprint(self.path)), encoding="utf-8")

    def save_merged(self, folder: str | Path) -> None:
        """Write the base weights with the merged start adapters, so that vLLM can serve them."""
        import shutil

        folder = Path(folder)
        shutil.rmtree(folder, ignore_errors=True)
        self.base.save_pretrained(folder)
        # The tokenizer, the chat template and the configs of other parts come from the base folder.
        for f in Path(self.path).iterdir():
            if f.is_file() and not (folder / f.name).exists() and f.suffix not in (".safetensors", ".bin", ".pt"):
                shutil.copy(f, folder / f.name)

    # Forward and backward

    @contextlib.contextmanager
    def _capture(self):
        """Replace the output layer for one forward pass, so that the logits come in chunks (see grpo.py)."""
        head = self.model.get_output_embeddings()
        parent_name, _, attr = next(n for n, m in self.model.named_modules() if m is head).rpartition(".")
        parent = self.model.get_submodule(parent_name)
        capture = _Capture(self.torch)
        setattr(parent, attr, capture.module)
        try:
            yield capture, head.weight
        finally:
            setattr(parent, attr, head)

    def logprobs(self, ids: list[int], mask: list[int]):
        """The log-probabilities of the tokens with mask 1, with gradients if the model trains."""
        torch = self.torch
        positions = [p for p, m in enumerate(mask) if m and p > 0]
        input_ids = torch.tensor([ids], device=self.device)
        keep = torch.tensor([p - 1 for p in positions], device=self.device)
        with self._capture() as (capture, weight), torch.autocast("cuda", dtype=torch.float16,
                                                                  enabled=torch.cuda.is_available()):
            self.model(input_ids=input_ids, logits_to_keep=keep, use_cache=False)
            return token_logprobs(capture.hidden[0], weight, input_ids[0, keep + 1], self.rl["logprob_chunk"],
                                  self.softcap, self.rl["temperature"])

    def sample(self, prompt: list[int], max_new: int, temperature: float) -> tuple[list[int], list[float]]:
        """Generate one turn. Return the sampled tokens and their log-probabilities."""
        torch = self.torch
        from transformers import LogitsProcessorList

        recorder = _Recorder(torch, temperature)
        sampling = ({"do_sample": True, "temperature": 1.0, "top_p": 1.0, "top_k": 0} if temperature > 0
                    else {"do_sample": False, "temperature": None, "top_p": None, "top_k": None})
        input_ids = torch.tensor([prompt], device=self.device)
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16, enabled=torch.cuda.is_available()):
            out = self.model.generate(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                                      max_new_tokens=max_new, logits_processor=LogitsProcessorList([recorder]),
                                      pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
                                      **sampling)
        new = out[0, len(prompt):].tolist()
        return new, recorder.finish(new[-1]) if new else []

    def free_memory(self) -> None:
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
