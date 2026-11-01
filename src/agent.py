"""Agent loop: one model does one task with the environment tools."""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Literal

import mcp
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "v1"
SYSTEM_PROMPT = """You are an assistant for a project management system. You can read and change the project board only with the tools.

Rules:
- Use the tools to find the facts and to make the changes. Do not guess keys or ids.
- The user names a person by a Polish first name, often in a short form or in a grammatical case, for example "Ani", "Kubie" or "Tomka". Use list_users to find the person id.
- "Otwarte" (open) issues are all issues with a status other than done.
- "Bieżący sprint" (the current sprint) is the sprint with the state active.
- "Następny sprint" (the next sprint) is the future sprint with the lowest number.
- "Backlog" means no sprint.
- Status words: "do zrobienia" is to_do. "W toku" and "w trakcie" are in_progress. "Zrobione", "zakończone" and "gotowe" are done.
- Make only the changes that the user asks for.
- Some tasks are not possible with the tools. Examples: a request outside the project board, an operation without a tool, a person or an issue that does not exist. For such a task, do not change the board. Start your answer with "ODMOWA:" and give a short reason.
- When the task is complete, answer the user in Polish in one or two sentences, without a tool call."""


class Call(BaseModel):
    id: str
    name: str
    arguments: dict | None
    raw: str = ""
    error: str | None = None


class ModelOutput(BaseModel):
    text: str
    calls: list[Call] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class ToolRecord(BaseModel):
    step: int
    name: str
    arguments: dict | str | None
    result: str
    is_error: bool
    invalid: bool = False


class Trajectory(BaseModel):
    task_id: str = ""
    instruction: str
    prompt_version: str = PROMPT_VERSION
    messages: list[dict] = Field(default_factory=list)
    tool_calls: list[ToolRecord] = Field(default_factory=list)
    final_answer: str = ""
    stop_reason: Literal["answer", "max_steps", "error"] = "answer"
    steps: int = 0
    invalid_calls: int = 0
    tool_errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    time_s: float = 0.0
    error: str | None = None


# Parser of Qwen3 tool calls: <tool_call>{"name": ..., "arguments": {...}}</tool_call>

TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)


def parse_output(text: str, step: int) -> tuple[str, list[Call]]:
    """Return the text without the tool calls, and the tool calls. A call that is not valid has an error."""
    text = THINK_RE.sub("", text)
    calls = []
    for n, match in enumerate(TOOL_CALL_RE.finditer(text)):
        raw = match.group(1).strip()
        call = Call(id=f"call_{step}_{n}", name="", arguments=None, raw=raw)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            call.error = f"The tool call is not valid JSON ({e.msg}). Write one JSON object with the keys name and arguments."
            calls.append(call)
            continue
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
        calls.append(call)
    return TOOL_CALL_RE.sub("", text).strip(), calls


def _simplify_schema(schema):
    """Remove titles and null alternatives, so that the tool schemas use fewer tokens."""
    if isinstance(schema, list):
        return [_simplify_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    schema = {k: _simplify_schema(v) for k, v in schema.items() if k != "title"}
    options = schema.get("anyOf")
    if options and {"type": "null"} in options:
        rest = [o for o in options if o != {"type": "null"}]
        if len(rest) == 1:
            del schema["anyOf"]
            schema = {**rest[0], **schema}
    if schema.get("default", 0) is None:
        del schema["default"]
    return schema


def tool_schema(tool) -> dict:
    """Convert an MCP tool to the OpenAI function format."""
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description or "", "parameters": _simplify_schema(tool.input_schema),
    }}


def _result_text(result) -> str:
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    try:
        return json.dumps(json.loads(text), ensure_ascii=False)
    except json.JSONDecodeError:
        return text


def _assistant_message(out: ModelOutput) -> dict:
    message = {"role": "assistant", "content": out.text}
    if out.calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.name, "arguments": c.arguments if c.arguments is not None else c.raw}}
            for c in out.calls
        ]
    return message


async def run_task_async(backend, server, instruction: str, max_steps: int = 15, task_id: str = "") -> Trajectory:
    start = time.perf_counter()
    traj = Trajectory(task_id=task_id, instruction=instruction)
    traj.messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": instruction}]
    try:
        async with mcp.Client(server) as client:
            listed = (await client.list_tools()).tools
            tools = [tool_schema(t) for t in listed]
            names = sorted(t.name for t in listed)
            traj.stop_reason = "max_steps"
            for step in range(1, max_steps + 1):
                out = backend.generate(traj.messages, tools, step)
                traj.steps = step
                traj.input_tokens += out.input_tokens
                traj.output_tokens += out.output_tokens
                traj.messages.append(_assistant_message(out))
                if not out.calls:
                    traj.final_answer, traj.stop_reason = out.text, "answer"
                    break
                for call in out.calls:
                    invalid = call.error is not None or call.name not in names
                    if call.error is not None:
                        result, is_error = f"Error: {call.error}", True
                    elif call.name not in names:
                        result, is_error = f"Error: unknown tool '{call.name}'. Available tools: {', '.join(names)}.", True
                    else:
                        response = await client.call_tool(call.name, call.arguments)
                        result, is_error = _result_text(response), bool(response.is_error)
                    traj.invalid_calls += invalid
                    traj.tool_errors += is_error and not invalid
                    traj.tool_calls.append(ToolRecord(step=step, name=call.name, result=result, is_error=is_error,
                                                      invalid=invalid,
                                                      arguments=call.arguments if call.arguments is not None else call.raw))
                    traj.messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": result})
    except Exception as e:  # noqa: BLE001  The evaluation grades this task as incorrect and continues.
        while isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:  # The MCP client adds a group.
            e = e.exceptions[0]
        traj.stop_reason, traj.error = "error", f"{type(e).__name__}: {e}"
    traj.time_s = round(time.perf_counter() - start, 3)
    return traj


def run_task(backend, server, instruction: str, max_steps: int = 15, task_id: str = "") -> Trajectory:
    return asyncio.run(run_task_async(backend, server, instruction, max_steps, task_id))


# Backends. Each backend has generate(messages, tools, step) -> ModelOutput and the attributes name and revision.

class ScriptedBackend:
    """Fixed outputs for the tests. `outputs` is a list of texts (the last text repeats) or a function (messages, step) -> text.
    An exception in the list is raised."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.name = self.revision = "scripted"

    def generate(self, messages, tools, step) -> ModelOutput:
        if callable(self.outputs):
            text = self.outputs(messages, step)
        else:
            text = self.outputs[min(step, len(self.outputs)) - 1]
        if isinstance(text, Exception):
            raise text
        content, calls = parse_output(text, step)
        words = sum(len(str(m.get("content", "")).split()) for m in messages)
        return ModelOutput(text=content, calls=calls, input_tokens=words, output_tokens=len(text.split()))


def render_prompt(tokenizer, messages: list[dict], tools: list[dict], enable_thinking: bool = False) -> str:
    return tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=True, tokenize=False,
                                         enable_thinking=enable_thinking)


def _cached_revision(name: str) -> str | None:
    """Return the commit hash of a Hub model from the path of its local snapshot."""
    from huggingface_hub import try_to_load_from_cache

    path = try_to_load_from_cache(name, "config.json")
    return Path(path).parent.name if isinstance(path, str) else None


class TransformersBackend:
    def __init__(self, name: str = "Qwen/Qwen3-1.7B", dtype: str = "float32", enable_thinking: bool = False,
                 max_new_tokens: int = 512, device: str | None = None, revision: str | None = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.name, self.enable_thinking, self.max_new_tokens = name, enable_thinking, max_new_tokens
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
        self.model = AutoModelForCausalLM.from_pretrained(name, dtype=getattr(torch, dtype), revision=revision)
        self.model.to(self.device).eval()
        self.revision = getattr(self.model.config, "_commit_hash", None) or _cached_revision(name) or revision

    def generate(self, messages, tools, step) -> ModelOutput:
        prompt = render_prompt(self.tokenizer, messages, tools, self.enable_thinking)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                                         temperature=None, top_p=None, top_k=None)
        new = output[0, inputs["input_ids"].shape[1]:]
        content, calls = parse_output(self.tokenizer.decode(new, skip_special_tokens=True), step)
        return ModelOutput(text=content, calls=calls, input_tokens=inputs["input_ids"].shape[1], output_tokens=len(new))


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


class OpenAIBackend:
    """A model behind an OpenAI-compatible API. The API key comes only from the environment variables or `.env`."""

    def __init__(self, name: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY", client=None):
        if client is None:
            from dotenv import load_dotenv
            from openai import OpenAI

            load_dotenv(ROOT / ".env")
            # A local server (for example Ollama) does not need a key, but the client needs a value.
            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env) or "none")
        self.client, self.name, self.revision = client, name, name

    def generate(self, messages, tools, step) -> ModelOutput:
        response = self.client.chat.completions.create(
            model=self.name, messages=to_openai_messages(messages), tools=tools, temperature=0,
        )
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
                           input_tokens=usage.prompt_tokens if usage else 0,
                           output_tokens=usage.completion_tokens if usage else 0)


def make_backend(model_cfg: dict):
    cfg = dict(model_cfg)
    backend = cfg.pop("backend")
    if backend == "transformers":
        return TransformersBackend(**cfg)
    if backend == "openai":
        return OpenAIBackend(**cfg)
    raise ValueError(f"Unknown backend '{backend}'. Use transformers or openai.")
