"""Agent loop: one model does one task with the environment tools."""

import asyncio
import json
import time
from typing import Literal

import mcp
from pydantic import BaseModel, Field

from src.models import Model, ModelOutput, Prompt, load_prompt

DEFAULT_PROMPT = "v3"
# The same call this many times in a row ends the task. A greedy model does not leave such a loop.
DEFAULT_LOOP_LIMIT = 3
# This many tool errors in a row end the task. A model that fails so often does not recover.
DEFAULT_ERROR_LIMIT = 5
# The hard limit of tool calls in one task. A valid or a broken call counts as one step.
DEFAULT_MAX_STEPS = 25


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
    prompt_version: str = ""
    prompt_sha256: str = ""
    messages: list[dict] = Field(default_factory=list)
    tool_calls: list[ToolRecord] = Field(default_factory=list)
    thinking: list[str] = Field(default_factory=list)
    final_answer: str = ""
    stop_reason: Literal["answer", "max_steps", "loop_same", "loop_errors", "error"] = "answer"
    steps: int = 0
    invalid_calls: int = 0
    tool_errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    time_s: float = 0.0
    error: str | None = None


def _simplify_schema(schema):
    """Remove titles and null defaults, so that the tool schemas use fewer tokens."""
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
    if "default" in schema and schema["default"] is None:
        del schema["default"]
    return schema


def tool_schema(tool) -> dict:
    """Convert an MCP tool to the OpenAI function format."""
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description or "", "parameters": _simplify_schema(tool.input_schema),
    }}


def _result_text(result) -> str:
    """The text of a tool result. A JSON result becomes one compact line, so that it uses fewer tokens."""
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


async def run_task_async(model: Model, server, instruction: str, prompt: Prompt | None = None,
                         max_steps: int = DEFAULT_MAX_STEPS, task_id: str = "",
                         loop_limit: int | None = DEFAULT_LOOP_LIMIT,
                         error_limit: int | None = DEFAULT_ERROR_LIMIT) -> Trajectory:
    start = time.perf_counter()
    prompt = prompt or load_prompt("system", DEFAULT_PROMPT)
    traj = Trajectory(task_id=task_id, instruction=instruction, prompt_version=prompt.version,
                      prompt_sha256=prompt.sha256)
    traj.messages = [{"role": "system", "content": prompt.text}, {"role": "user", "content": instruction}]
    try:
        async with mcp.Client(server) as client:
            listed = (await client.list_tools()).tools
            tools = [tool_schema(t) for t in listed]
            names = sorted(t.name for t in listed)
            traj.stop_reason = "max_steps"
            streak, last, errors, stop = 0, None, 0, False
            for step in range(1, max_steps + 1):
                out = model.generate(traj.messages, tools)
                traj.steps = step
                traj.input_tokens += out.input_tokens
                traj.output_tokens += out.output_tokens
                if out.thinking_text:
                    traj.thinking.append(out.thinking_text)
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
                    key = (call.name, json.dumps(call.arguments, sort_keys=True) if call.arguments is not None else call.raw)
                    streak = streak + 1 if key == last else 1
                    last = key
                    errors = errors + 1 if is_error else 0
                    # Check after each call. One output can have many calls, and its last call can reset the counts.
                    if loop_limit and streak >= loop_limit:
                        traj.stop_reason, stop = "loop_same", True
                    elif error_limit and errors >= error_limit:
                        traj.stop_reason, stop = "loop_errors", True
                    elif len(traj.tool_calls) >= max_steps:
                        stop = True
                    if stop:
                        break
                if stop:
                    break
    except Exception as e:  # noqa: BLE001  The evaluation grades this task as incorrect and continues.
        while isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:  # The MCP client adds a group.
            e = e.exceptions[0]
        traj.stop_reason, traj.error = "error", f"{type(e).__name__}: {e}"
    traj.time_s = round(time.perf_counter() - start, 3)
    return traj


def run_task(model: Model, server, instruction: str, prompt: Prompt | None = None,
             max_steps: int = DEFAULT_MAX_STEPS, task_id: str = "",
             loop_limit: int | None = DEFAULT_LOOP_LIMIT, error_limit: int | None = DEFAULT_ERROR_LIMIT) -> Trajectory:
    return asyncio.run(run_task_async(model, server, instruction, prompt, max_steps, task_id, loop_limit, error_limit))
