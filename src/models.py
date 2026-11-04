"""Model layer: one interface for all models (design D14, D15).

A family makes the prompt with the chat template and finds the tool calls in the output text.
A backend runs the model: `transformers`, an OpenAI-compatible API, or fixed outputs for the tests.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "prompts"
BACKENDS = ("transformers", "openai", "scripted")


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

    @property
    def parse_errors(self) -> list[str]:
        return [c.error for c in self.calls if c.error]


class Prompt(BaseModel):
    version: str
    text: str
    sha256: str


def load_prompt(kind: str, version: str) -> Prompt:
    """Read `prompts/<kind>-<version>.md`. An unknown version stops with an error that names the file."""
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

    def render(self, tokenizer, messages: list[dict], tools: list[dict], thinking: bool) -> str:
        messages, tools = self.prepare(messages, tools)
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


class Bielik(Family):
    """Bielik has no native tool calls. The system prompt gives the tools and the format <tool_call>{json}</tool_call>."""

    name = "bielik"
    has_thinking = False
    end_markers = ("<|im_end|>", "</s>")
    CALL_RE = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.DOTALL)
    TOOLS_PROMPT = "v1"

    def tools_prompt(self, tools: list[dict]) -> str:
        listed = "\n".join(json.dumps(t.get("function", t), ensure_ascii=False) for t in tools)
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


def load_weights(path: str, revision: str | None, dtype: str):
    """Load the tokenizer and the model. A local folder loads without the internet."""
    import torch
    import transformers

    local = Path(path).is_dir()
    kwargs = {"local_files_only": True} if local else {"revision": revision}
    tokenizer = transformers.AutoTokenizer.from_pretrained(path, **kwargs)
    try:
        model = transformers.AutoModelForCausalLM.from_pretrained(path, dtype=getattr(torch, dtype), **kwargs)
    except ValueError:
        # The multimodal models (Gemma 4, Qwen3.5) can need the image-text class.
        model = transformers.AutoModelForImageTextToText.from_pretrained(path, dtype=getattr(torch, dtype), **kwargs)
    return tokenizer, model


class LocalModel(Model):
    backend = "transformers"

    def __init__(self, family: str, path: str, revision: str | None = None, thinking: bool = False,
                 dtype: str = "bfloat16", max_new_tokens: int = 1024, device: str | None = None):
        import torch

        super().__init__(get_family(family), path, revision, thinking)
        self.torch, self.max_new_tokens = torch, max_new_tokens
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer, self.model = load_weights(path, revision, dtype)
        self.model.to(self.device).eval()
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

    def __init__(self, path: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY",
                 family: str | None = None, thinking: bool = False, revision: str | None = None, client=None):
        super().__init__(get_family(family) if family else None, path, revision or path, thinking)
        if client is None:
            from dotenv import load_dotenv
            from openai import OpenAI

            load_dotenv(ROOT / ".env")
            # A local server (for example Ollama) does not need a key, but the client needs a value.
            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env) or "none")
        self.client = client

    def generate(self, messages, tools):
        self.steps += 1
        extra = {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}} if self.thinking else {}
        response = self.client.chat.completions.create(
            model=self.path, messages=to_openai_messages(messages), tools=tools, temperature=0, **extra)
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
        return ModelOutput(text=message.content or "", calls=calls,
                           thinking_text=getattr(message, "reasoning_content", None) or "",
                           input_tokens=usage.prompt_tokens if usage else 0,
                           output_tokens=usage.completion_tokens if usage else 0)


def check_config(cfg: dict) -> dict:
    """Check the `model` section of a run config before the first task. Return it with the defaults."""
    cfg = {"thinking": False, **cfg}
    if cfg.get("backend") not in BACKENDS:
        raise ValueError(f"Unknown backend '{cfg.get('backend')}'. Use {', '.join(BACKENDS)}.")
    if cfg.get("family") is not None or cfg["backend"] != "openai":
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
    return ApiModel(cfg["path"], base_url=cfg.get("base_url"), api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
                    family=cfg.get("family"), thinking=cfg["thinking"], revision=cfg.get("revision"))
