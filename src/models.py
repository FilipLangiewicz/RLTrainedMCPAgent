"""Model layer: one interface for all models (design D14, D15).

A family makes the prompt with the chat template and finds the tool calls in the output text.
A backend runs the model: `transformers`, an OpenAI-compatible API, the `claude` command, or fixed outputs for the tests.
"""

import gc
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "src" / "prompts"
BACKENDS = ("transformers", "openai", "claude_cli", "scripted")


class Call(BaseModel):
    id: str
    name: str
    arguments: dict | None
    raw: str = ""
    error: str | None = None


class ModelOutput(BaseModel):
    text: str
    calls: list[Call] = Field(default_factory=list)
    thinking_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def parse_errors(self) -> list[str]:
        return [c.error for c in self.calls if c.error]


class Prompt(BaseModel):
    version: str
    text: str
    sha256: str


def load_prompt(kind: str, version: str) -> Prompt:
    """Read `src/prompts/<kind>-<version>.md`. An unknown version stops with an error that names the file."""
    path = PROMPTS_DIR / f"{kind}-{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt file {path} does not exist")
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return Prompt(version=version, text=data.decode("utf-8").strip(), sha256=hashlib.sha256(data).hexdigest())


# Families

def _schema_types(tools: list[dict] | None) -> dict[str, dict[str, str]]:
    """Tool name -> argument name -> JSON type, from tools in the OpenAI function format."""
    result = {}
    for tool in tools or []:
        fn = tool.get("function", tool)
        props = (fn.get("parameters") or {}).get("properties", {})
        result[fn["name"]] = {k: v.get("type", "") for k, v in props.items()}
    return result


def _json_call(raw: str, n: int, step: int) -> Call:
    """A call in the format {"name": ..., "arguments": {...}}."""
    call = Call(id=f"call_{step}_{n}", name="", arguments=None, raw=raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        call.error = f"The tool call is not valid JSON ({e.msg}). Write one JSON object with the keys name and arguments."
        return call
    args = obj.get("arguments", {}) if isinstance(obj, dict) else None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = None
    if not isinstance(obj, dict) or not isinstance(obj.get("name"), str) or not isinstance(args, dict):
        call.error = "A tool call must be a JSON object with a string name and an object arguments."
    else:
        call.name, call.arguments = obj["name"], args
    return call


class Family:
    name = ""
    has_thinking = False
    end_markers: tuple[str, ...] = ()

    def prepare(self, messages: list[dict], tools: list[dict]) -> tuple[list[dict], list[dict] | None]:
        """The messages and the tools for the chat template."""
        return messages, tools

    def template_args(self, thinking: bool) -> dict:
        return {"enable_thinking": thinking} if self.has_thinking else {}

    @staticmethod
    def _with_mapping_arguments(messages: list[dict]) -> list[dict]:
        """The chat templates read the arguments of a call as a mapping. The text of a broken call would stop them."""
        result = []
        for m in messages:
            if m.get("tool_calls"):
                calls = [{**c, "function": {**c["function"], "arguments": c["function"]["arguments"]
                                            if isinstance(c["function"]["arguments"], dict) else {}}}
                         for c in m["tool_calls"]]
                m = {**m, "tool_calls": calls}
            result.append(m)
        return result

    def render(self, tokenizer, messages: list[dict], tools: list[dict], thinking: bool) -> str:
        messages, tools = self.prepare(self._with_mapping_arguments(messages), tools)
        return tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=True, tokenize=False,
                                             **self.template_args(thinking))

    def clean(self, text: str) -> str:
        for marker in self.end_markers:
            text = text.replace(marker, "")
        return text

    def parse(self, text: str, tools: list[dict] | None = None, step: int = 0) -> tuple[str, list[Call], str]:
        """Return the answer text without the calls, the calls and the thinking text."""
        raise NotImplementedError

    def format_calls(self, calls: list[dict]) -> str:
        """The text of the calls ({"name", "arguments"}) in the format of the family. The tests use it."""
        raise NotImplementedError


class Qwen35(Family):
    """Qwen3.5: <tool_call><function=name><parameter=arg>value</parameter></function></tool_call>."""

    name = "qwen3.5"
    has_thinking = True
    end_markers = ("<|im_end|>", "<|endoftext|>")
    CALL_RE = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.DOTALL)
    FUNCTION_RE = re.compile(r"<function=([^>\s]+)>(.*?)(?:</function>|$)", re.DOTALL)
    PARAM_RE = re.compile(r"<parameter=([^>\s]+)>(.*?)(?:</parameter>|$)", re.DOTALL)

    @staticmethod
    def _split_thinking(text: str) -> tuple[str, str]:
        if "</think>" not in text:
            return text, ""
        thinking, text = text.split("</think>", 1)
        return text, thinking.replace("<think>", "").strip()

    @staticmethod
    def _value(raw: str, kind: str):
        raw = raw.removeprefix("\n")
        raw = raw.removesuffix("\n")
        if kind == "string":
            return raw
        if kind == "integer":
            return int(raw.strip())
        if kind == "number":
            return float(raw.strip())
        if kind == "boolean":
            if raw.strip().lower() not in ("true", "false"):
                raise ValueError(f"'{raw}' is not a boolean")
            return raw.strip().lower() == "true"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if kind in ("object", "array"):
                raise
            return raw

    def parse(self, text, tools=None, step=0):
        text, thinking = self._split_thinking(text)
        types_ = _schema_types(tools)
        calls = []
        for n, match in enumerate(self.CALL_RE.finditer(text)):
            raw = match.group(1).strip()
            call = Call(id=f"call_{step}_{n}", name="", arguments=None, raw=raw)
            fn = self.FUNCTION_RE.search(raw)
            if fn is None:
                call.error = "A tool call must have a <function=name> block with <parameter=name> blocks."
            else:
                name, body = fn.group(1), fn.group(2)
                try:
                    args = {p: self._value(v, types_.get(name, {}).get(p, ""))
                            for p, v in self.PARAM_RE.findall(body)}
                    call.name, call.arguments = name, args
                except (ValueError, json.JSONDecodeError) as e:
                    call.error = f"An argument of the tool call {name} has a wrong value ({e})."
            calls.append(call)
        return self.CALL_RE.sub("", text).strip(), calls, thinking

    def format_calls(self, calls):
        parts = []
        for c in calls:
            params = "".join(
                f"<parameter={k}>\n{json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v}\n</parameter>\n"
                for k, v in c["arguments"].items())
            parts.append(f"<tool_call>\n<function={c['name']}>\n{params}</function>\n</tool_call>")
        return "\n".join(parts)


class _GemmaArgs:
    """Parser of the argument syntax of Gemma 4: {key:value,...}, strings in <|"|>, lists in []."""

    QUOTE = '<|"|>'

    def __init__(self, text: str):
        self.text, self.pos = text, 0

    def fail(self, what: str):
        raise ValueError(f"{what} at position {self.pos}")

    def skip(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def value(self):
        self.skip()
        t = self.text
        if t.startswith(self.QUOTE, self.pos):
            end = t.find(self.QUOTE, self.pos + len(self.QUOTE))
            if end < 0:
                self.fail("text without an end mark")
            value = t[self.pos + len(self.QUOTE): end]
            self.pos = end + len(self.QUOTE)
            return value
        if t.startswith("{", self.pos):
            return self.obj()
        if t.startswith("[", self.pos):
            self.pos += 1
            items = []
            self.skip()
            if t.startswith("]", self.pos):
                self.pos += 1
                return items
            while True:
                items.append(self.value())
                self.skip()
                if t.startswith(",", self.pos):
                    self.pos += 1
                elif t.startswith("]", self.pos):
                    self.pos += 1
                    return items
                else:
                    self.fail("expected ',' or ']'")
        m = re.compile(r"-?\d+(?:\.\d+)?|true|false|null").match(t, self.pos)
        if not m:
            self.fail("unexpected value")
        self.pos = m.end()
        return json.loads(m.group(0))

    def obj(self) -> dict:
        t = self.text
        if not t.startswith("{", self.pos):
            self.fail("expected '{'")
        self.pos += 1
        result = {}
        self.skip()
        if t.startswith("}", self.pos):
            self.pos += 1
            return result
        while True:
            self.skip()
            if t.startswith(self.QUOTE, self.pos):
                key = self.value()
            else:
                m = re.compile(r"[\w.-]+").match(t, self.pos)
                if not m:
                    self.fail("expected a key")
                key, self.pos = m.group(0), m.end()
            self.skip()
            if not t.startswith(":", self.pos):
                self.fail("expected ':'")
            self.pos += 1
            result[key] = self.value()
            self.skip()
            if t.startswith(",", self.pos):
                self.pos += 1
            elif t.startswith("}", self.pos):
                self.pos += 1
                return result
            else:
                self.fail("expected ',' or '}'")


class Gemma4(Family):
    """Gemma 4: <|tool_call>call:name{key:<|"|>text<|"|>,n:5}<tool_call|>."""

    name = "gemma4"
    has_thinking = True
    end_markers = ("<turn|>", "<|tool_response>", "<eos>", "<end_of_turn>")
    CALL_RE = re.compile(r"<\|tool_call>call:([\w.-]+)(.*?)(?:<tool_call\|>|$)", re.DOTALL)
    THINK_RE = re.compile(r"<\|channel>(?:thought)?\s*(.*?)(?:<channel\|>|$)", re.DOTALL)

    def parse(self, text, tools=None, step=0):
        thinking = "\n".join(m.strip() for m in self.THINK_RE.findall(text))
        text = self.THINK_RE.sub("", text)
        calls = []
        for n, match in enumerate(self.CALL_RE.finditer(text)):
            name, body = match.group(1), match.group(2).strip()
            call = Call(id=f"call_{step}_{n}", name="", arguments=None, raw=match.group(0))
            try:
                parser = _GemmaArgs(body)
                args = parser.obj()
                parser.skip()
                if parser.pos != len(body):
                    parser.fail("text after the arguments")
                call.name, call.arguments = name, args
            except ValueError as e:
                call.error = f"The arguments of the tool call {name} are not valid ({e})."
            calls.append(call)
        return self.CALL_RE.sub("", text).strip(), calls, thinking

    @classmethod
    def _format(cls, value) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return f'{_GemmaArgs.QUOTE}{value}{_GemmaArgs.QUOTE}'
        if isinstance(value, dict):
            return "{" + ",".join(f"{k}:{cls._format(v)}" for k, v in sorted(value.items())) + "}"
        if isinstance(value, list):
            return "[" + ",".join(cls._format(v) for v in value) + "]"
        return str(value)

    def format_calls(self, calls):
        return "".join(f"<|tool_call>call:{c['name']}{self._format(c['arguments'])}<tool_call|>" for c in calls)


def _first_sentence(text: str, limit: int) -> str:
    """The first line or sentence of a description, cut to `limit` characters."""
    text = (text or "").strip().split("\n")[0]
    text = re.split(r"(?<=\.)\s(?=[A-Z])", text)[0]
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def compact_tool(tool: dict) -> str:
    """One tool as short text: the signature, the description and one line for each argument."""
    properties = tool.get("parameters", {}).get("properties", {})
    required = set(tool.get("parameters", {}).get("required", []))
    signature = ", ".join(k if k in required else f"{k}?" for k in properties)
    lines = [f"- {tool['name']}({signature}): {_first_sentence(tool.get('description', ''), 200)}"]
    for key, spec in properties.items():
        kind = "|".join(map(str, spec["enum"])) if "enum" in spec else spec.get("type", "any")
        lines.append(f"    {key} ({kind}): {_first_sentence(spec.get('description', ''), 160)}")
    return "\n".join(lines)


class Bielik(Family):
    """Bielik has no native tool calls. The system prompt gives the tools and the format <tool_call>{json}</tool_call>."""

    name = "bielik"
    has_thinking = False
    end_markers = ("<|im_end|>", "</s>")
    CALL_RE = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.DOTALL)
    TOOLS_PROMPT = "v2"

    def tools_prompt(self, tools: list[dict]) -> str:
        # The full JSON schemas of the 14 tools need more than 7000 tokens with the Bielik tokenizer.
        listed = "\n".join(compact_tool(t.get("function", t)) for t in tools)
        return load_prompt("tools-bielik", self.TOOLS_PROMPT).text.replace("{tools}", listed)

    def prepare(self, messages, tools):
        result = []
        for m in messages:
            if m["role"] == "system":
                result.append({"role": "system", "content": m["content"] + "\n\n" + self.tools_prompt(tools)})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                calls = self.format_calls([c["function"] for c in m["tool_calls"]])
                result.append({"role": "assistant", "content": (m["content"] + "\n" + calls).strip()})
            elif m["role"] == "tool":
                block = f"<tool_response>\n{m['content']}\n</tool_response>"
                if result and result[-1]["role"] == "user" and result[-1]["content"].startswith("<tool_response>"):
                    result[-1] = {"role": "user", "content": result[-1]["content"] + "\n" + block}
                else:
                    result.append({"role": "user", "content": block})
            else:
                result.append({"role": m["role"], "content": m["content"]})
        return result, None

    def parse(self, text, tools=None, step=0):
        calls = [_json_call(m.group(1).strip(), n, step) for n, m in enumerate(self.CALL_RE.finditer(text))]
        return self.CALL_RE.sub("", text).strip(), calls, ""

    def format_calls(self, calls):
        return "\n".join(
            f"<tool_call>{json.dumps({'name': c['name'], 'arguments': c['arguments']}, ensure_ascii=False)}</tool_call>"
            for c in calls)


FAMILIES = {f.name: f for f in (Qwen35(), Gemma4(), Bielik())}


def get_family(name: str | None) -> Family:
    if name not in FAMILIES:
        raise ValueError(f"Unknown model family '{name}'. Use {', '.join(FAMILIES)}.")
    return FAMILIES[name]


# Backends. Each model has generate(messages, tools) -> ModelOutput and the attributes of `describe()`.

class Model:
    backend = ""

    def __init__(self, family: Family | None, path: str, revision: str | None, thinking: bool):
        self.family, self.path, self.revision, self.thinking = family, path, revision, thinking
        self.steps = 0

    @property
    def name(self) -> str:
        return self.path

    def describe(self) -> dict:
        return {"backend": self.backend, "family": self.family.name if self.family else None, "path": self.path,
                "revision": self.revision, "thinking": self.thinking}

    def generate(self, messages: list[dict], tools: list[dict]) -> ModelOutput:
        raise NotImplementedError

    def free_memory(self) -> None:
        """Free the memory of a failed task. Only a local model needs this."""


class ScriptedModel(Model):
    """Fixed outputs for the tests. `outputs` is a list of texts (the last text repeats) or a function
    (messages, step) -> text. An exception in the list is raised. The text goes through the parser of the family."""

    backend = "scripted"

    def __init__(self, outputs, family: str = "qwen3.5", thinking: bool = False):
        super().__init__(get_family(family), "scripted", "scripted", thinking)
        self.outputs = outputs

    def generate(self, messages, tools):
        self.steps += 1
        if callable(self.outputs):
            text = self.outputs(messages, self.steps)
        else:
            text = self.outputs[min(self.steps, len(self.outputs)) - 1]
        if isinstance(text, Exception):
            raise text
        content, calls, thinking = self.family.parse(text, tools, self.steps)
        words = sum(len(str(m.get("content", "")).split()) for m in messages)
        return ModelOutput(text=content, calls=calls, thinking_text=thinking, input_tokens=words,
                           output_tokens=len(text.split()))


def load_weights(path: str, revision: str | None, dtype: str, device_map: str | None = None):
    """Load the tokenizer and the model. A local folder loads without the internet."""
    import torch
    import transformers

    # The bar "Loading weights" writes hundreds of lines into the log of a job.
    transformers.utils.logging.disable_progress_bar()
    local = Path(path).is_dir()
    kwargs = {"local_files_only": True} if local else {"revision": revision}
    if device_map:
        kwargs["device_map"] = device_map
    tokenizer = transformers.AutoTokenizer.from_pretrained(path, **kwargs)
    try:
        model = transformers.AutoModelForCausalLM.from_pretrained(path, dtype=getattr(torch, dtype), **kwargs)
    except ValueError:
        # The multimodal models (Gemma 4, Qwen3.5) can need the image-text class.
        model = transformers.AutoModelForImageTextToText.from_pretrained(path, dtype=getattr(torch, dtype), **kwargs)
    return tokenizer, model


def avoid_gqa_in_sdpa() -> None:
    """On a GPU older than Ampere (for example a T4), repeat the key and value heads before the attention.

    Without it, PyTorch uses the math kernel for grouped-query attention. This kernel builds a full
    attention matrix in float32 and runs out of GPU memory for a prompt of 10000 tokens.
    """
    import torch

    if torch.cuda.is_available() and torch.cuda.get_device_capability()[0] < 8:
        import transformers.integrations.sdpa_attention as sdpa

        sdpa.use_gqa_in_sdpa = lambda *args, **kwargs: False


class LocalModel(Model):
    backend = "transformers"

    def __init__(self, family: str, path: str, revision: str | None = None, thinking: bool = False,
                 dtype: str = "bfloat16", max_new_tokens: int = 1024, device: str | None = None):
        import torch

        super().__init__(get_family(family), path, revision, thinking)
        self.torch, self.max_new_tokens = torch, max_new_tokens
        # The device "auto" splits a model that is too large for one GPU over all GPUs.
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        avoid_gqa_in_sdpa()
        self.tokenizer, self.model = load_weights(path, revision, dtype, "auto" if self.device == "auto" else None)
        if self.device == "auto":
            self.device = self.model.device
        else:
            self.model.to(self.device)
        self.model.eval()
        self.revision = revision or getattr(self.model.config, "_commit_hash", None)

    def generate(self, messages, tools):
        self.steps += 1
        prompt = self.family.render(self.tokenizer, messages, tools, self.thinking)
        inputs = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(self.device)
        with self.torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                                         temperature=None, top_p=None, top_k=None)
        new = output[0, inputs["input_ids"].shape[1]:]
        # The tool-call marks of some families are special tokens, so the decode keeps them.
        text = self.tokenizer.decode(new, skip_special_tokens=False)
        for token in {self.tokenizer.eos_token, self.tokenizer.pad_token, self.tokenizer.bos_token} - {None}:
            text = text.replace(token, "")
        content, calls, thinking = self.family.parse(self.family.clean(text), tools, self.steps)
        return ModelOutput(text=content, calls=calls, thinking_text=thinking,
                           input_tokens=inputs["input_ids"].shape[1], output_tokens=len(new))

    def free_memory(self):
        # The traceback of an error keeps the tensors of `generate` in reference cycles. The automatic
        # collection can leave them alive for many tasks, and then each next task runs out of memory.
        allocated = self.torch.cuda.memory_allocated() if self.torch.cuda.is_available() else 0
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
            print(f"free_memory: allocated {allocated} -> {self.torch.cuda.memory_allocated()} bytes", flush=True)


def to_openai_messages(messages: list[dict]) -> list[dict]:
    result = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = [{"id": c["id"], "type": "function", "function": {
                "name": c["function"]["name"],
                "arguments": c["function"]["arguments"] if isinstance(c["function"]["arguments"], str)
                else json.dumps(c["function"]["arguments"], ensure_ascii=False),
            }} for c in m["tool_calls"]]
            result.append({"role": "assistant", "content": m["content"] or None, "tool_calls": calls})
        elif m["role"] == "tool":
            result.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        else:
            result.append({"role": m["role"], "content": m["content"]})
    return result


class ApiModel(Model):
    """A model behind an OpenAI-compatible API. The API key comes only from the environment variables or `.env`."""

    backend = "openai"

    MAX_WAIT_S = 120  # A longer wait means a daily limit. The run stops, and --resume continues it later.
    MAX_ATTEMPTS = 8

    def __init__(self, path: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY",
                 family: str | None = None, thinking: bool = False, revision: str | None = None, client=None,
                 prices: dict | None = None, temperature: float | None = 0, reasoning_effort: str | None = None):
        super().__init__(get_family(family) if family else None, path, revision or path, thinking)
        self.prices = prices or {}
        self.options = {"temperature": temperature, "reasoning_effort": reasoning_effort}
        if client is None:
            from dotenv import load_dotenv
            from openai import OpenAI

            load_dotenv(ROOT / ".env")
            # A local server (for example Ollama) does not need a key, but the client needs a value.
            # This class does its own retries, so that a limit never gives a false grade.
            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env) or "none", max_retries=0)
        self.client = client

    def generate(self, messages, tools):
        self.steps += 1
        extra = {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}} if self.thinking else {}
        options = {k: v for k, v in self.options.items() if v is not None}
        response = self._create(model=self.path, messages=to_openai_messages(messages), tools=tools, **options, **extra)
        message = response.choices[0].message
        calls = []
        for tc in message.tool_calls or []:
            raw = tc.function.arguments or "{}"
            call = Call(id=tc.id, name=tc.function.name, arguments=None, raw=raw)
            try:
                args = json.loads(raw)
                if isinstance(args, dict):
                    call.arguments = args
                else:
                    call.error = "The arguments of a tool call must be a JSON object."
            except json.JSONDecodeError as e:
                call.error = f"The arguments of the tool call are not valid JSON ({e.msg})."
            calls.append(call)
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0
        cost = ((tokens_in - cached) * self.prices.get("input", 0) + cached * self.prices.get("cached_input", 0)
                + tokens_out * self.prices.get("output", 0)) / 1_000_000
        # A proxy can give the real cost of the call. This value is better than a price in a config.
        billed = getattr(usage, "cost", None) or {}
        if billed:
            cost = sum(billed.get(f"{k}_tokens_cost_nanodollars") or 0 for k in ("input", "output")) / 1e9
        return ModelOutput(text=message.content or "", calls=calls,
                           thinking_text=getattr(message, "reasoning_content", None) or "",
                           input_tokens=tokens_in, output_tokens=tokens_out, cached_input_tokens=cached, cost_usd=cost)

    def _create(self, **request):
        """Wait for a short limit. Stop the run at a long limit or a server failure, so that no task gets a false grade."""
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                response = self.client.chat.completions.create(**request)
                if response.choices and response.choices[0].message is not None:
                    return response
                # A response without a message is a failure of the service, not a failure of the model.
                print(f"no message in the response: wait {2 ** attempt} s", flush=True)
                time.sleep(2 ** attempt)
            except Exception as e:  # The next lines select the failures of the service.
                response = getattr(e, "response", None)
                status = getattr(response, "status_code", None)
                if status in (401, 402, 403):
                    raise ModelStopped(f"no budget or no access, status {status}: {str(e)[:300]}") from e
                if status is not None and status != 429 and status < 500:
                    raise
                if status is None and type(e).__name__ not in ("APIConnectionError", "APITimeoutError"):
                    raise
                wait = float((response.headers.get("retry-after") if response is not None else None) or 2 ** attempt)
                if wait > self.MAX_WAIT_S:
                    raise ModelStopped(f"limit of the service, wait {wait:.0f} s: {str(e)[:300]}") from e
                print(f"status {status}: wait {wait:.0f} s", flush=True)
                time.sleep(wait)
        raise ModelStopped(f"the service failed {self.MAX_ATTEMPTS} times")


class ModelStopped(Exception):
    """The model cannot continue. The run must stop, because the next tasks would get false grades."""


class ClaudeCliModel(Model):
    """A reference model behind the `claude` command. The command uses the limits of the plan of the logged-in user.

    Each step is a new process without tools, with the full conversation as text. The agent loop runs the tools.
    The tools and the format of a call are the same as for Bielik. Thus this model gets no new prompt.
    """

    backend = "claude_cli"
    # An API key in the environment would make the command use a paid account.
    REMOVED_ENV_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDECODE")
    # The rules and the memory of the user must not change the prompt of the test.
    ADDED_ENV = (("CLAUDE_CODE_DISABLE_CLAUDE_MDS", "1"), ("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1"))

    def __init__(self, path: str, effort: str = "medium", command: str = "claude", timeout_s: int = 120, attempts: int = 3):
        self.command, self.effort, self.timeout_s, self.attempts = command, effort, timeout_s, attempts
        self.parser = get_family("bielik")
        super().__init__(None, path, self._version(), False)
        self.workdir = tempfile.mkdtemp(prefix="claude-cli-")

    def _version(self) -> str:
        try:
            return subprocess.run([self.command, "--version"], capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as e:
            raise ModelStopped(f"the command '{self.command}' does not operate: {e}") from e

    def describe(self) -> dict:
        tools_prompt = load_prompt("tools-bielik", self.parser.TOOLS_PROMPT)
        return {**super().describe(), "effort": self.effort, "tools_prompt": tools_prompt.version,
                "tools_prompt_sha256": tools_prompt.sha256}

    def render(self, messages: list[dict], tools: list[dict]) -> tuple[str, str]:
        """Return the system prompt and the conversation as text."""
        turns, _ = self.parser.prepare(messages, tools)
        return turns[0]["content"], "\n\n".join(f"<{m['role']}>\n{m['content']}\n</{m['role']}>" for m in turns[1:])

    def arguments(self, system: str) -> list[str]:
        return [self.command, "-p", "--model", self.path, "--effort", self.effort, "--output-format", "json",
                "--system-prompt", system, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
                "--disable-slash-commands", "--no-session-persistence"]

    def environment(self) -> dict:
        kept = {k: v for k, v in os.environ.items() if not k.startswith(self.REMOVED_ENV_PREFIXES)}
        return {**kept, **dict(self.ADDED_ENV)}

    def _run(self, system: str, conversation: str):
        # The stream of an answer can stop and the process then waits forever. A new attempt of the step is safe.
        for attempt in range(1, self.attempts + 1):
            try:
                return subprocess.run(self.arguments(system), input=conversation, capture_output=True, text=True,
                                      encoding="utf-8", cwd=self.workdir, env=self.environment(),
                                      timeout=self.timeout_s, check=False)
            except subprocess.TimeoutExpired:
                print(f"no answer in {self.timeout_s} s, attempt {attempt} of {self.attempts}", flush=True)
            except OSError as e:
                raise ModelStopped(f"the command failed: {e}") from e
        raise ModelStopped(f"no answer after {self.attempts} attempts")

    def generate(self, messages, tools):
        self.steps += 1
        system, conversation = self.render(messages, tools)
        done = self._run(system, conversation)
        try:
            data = json.loads(done.stdout)
        except json.JSONDecodeError as e:
            raise ModelStopped(f"exit code {done.returncode}: {(done.stdout + done.stderr)[:500]}") from e
        if done.returncode != 0 or data.get("is_error"):
            raise ModelStopped(f"exit code {done.returncode}: {str(data.get('result'))[:500]}")
        used = data.get("modelUsage") or {}
        if used and not any(name.startswith(self.path) for name in used):
            raise ModelStopped(f"the answer came from {sorted(used)}, not from {self.path}")
        # No stop sequence exists here. Thus the model can write a false tool result after its call.
        text = re.split(r"<tool_response>|<user>", data.get("result") or "", maxsplit=1)[0]
        text = re.sub(r"</?assistant>", "", text)
        answer, calls, _ = self.parser.parse(text, tools, self.steps)
        usage = data.get("usage") or {}
        # On a plan, this cost is the price of the same tokens on the API. The plan does not bill it.
        return ModelOutput(text=answer, calls=calls,
                           input_tokens=sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                      "cache_read_input_tokens")),
                           cached_input_tokens=usage.get("cache_read_input_tokens", 0),
                           output_tokens=usage.get("output_tokens", 0), cost_usd=data.get("total_cost_usd") or 0.0)


def check_config(cfg: dict) -> dict:
    """Check the `model` section of a run config before the first task. Return it with the defaults."""
    cfg = {"thinking": False, **cfg}
    if cfg.get("backend") not in BACKENDS:
        raise ValueError(f"Unknown backend '{cfg.get('backend')}'. Use {', '.join(BACKENDS)}.")
    if cfg.get("family") is not None or cfg["backend"] not in ("openai", "claude_cli"):
        family = get_family(cfg.get("family"))
        if cfg["thinking"] and not family.has_thinking:
            raise ValueError(f"The model family '{family.name}' has no thinking mode. Set model.thinking to false.")
    return cfg


def make_model(cfg: dict, outputs=None) -> Model:
    """Build the model from the `model` section of a run config. `outputs` is for the `scripted` backend."""
    cfg = check_config(cfg)
    backend = cfg["backend"]
    if backend == "scripted":
        return ScriptedModel(outputs or [""], family=cfg["family"], thinking=cfg["thinking"])
    if backend == "transformers":
        return LocalModel(cfg["family"], cfg["path"], revision=cfg.get("revision"), thinking=cfg["thinking"],
                          dtype=cfg.get("dtype", "bfloat16"), max_new_tokens=cfg.get("max_new_tokens", 1024),
                          device=cfg.get("device"))
    if backend == "claude_cli":
        return ClaudeCliModel(cfg["path"], effort=cfg.get("effort", "medium"))
    return ApiModel(cfg["path"], base_url=cfg.get("base_url"), api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
                    family=cfg.get("family"), thinking=cfg["thinking"], revision=cfg.get("revision"),
                    prices=cfg.get("prices"), temperature=cfg.get("temperature", 0),
                    reasoning_effort=cfg.get("reasoning_effort"))
