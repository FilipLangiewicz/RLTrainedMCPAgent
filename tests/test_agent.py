import asyncio
import json
from types import SimpleNamespace

import mcp
import pytest

from src.agent import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    OpenAIBackend,
    ScriptedBackend,
    Trajectory,
    parse_output,
    render_prompt,
    run_task,
    tool_schema,
)
from src.environment import generate_board
from src.tools import build_server


def tc(name, **arguments):
    return f'<tool_call>\n{json.dumps({"name": name, "arguments": arguments})}\n</tool_call>'


@pytest.fixture
def board():
    return generate_board("test-x", "WEB", seed=2)


def tools_of(board):
    async def go():
        async with mcp.Client(build_server(board)) as client:
            return [tool_schema(t) for t in (await client.list_tools()).tools]
    return asyncio.run(go())


def test_final_answer(board):
    backend = ScriptedBackend([tc("update_issue", key="WEB-1", priority="critical"), "Gotowe, zmieniłem priorytet."])
    traj = run_task(backend, build_server(board), "Ustaw WEB-1 priorytet krytyczny.", task_id="t1")
    assert traj.stop_reason == "answer"
    assert traj.final_answer == "Gotowe, zmieniłem priorytet."
    assert traj.steps == 2
    assert board.issue("WEB-1").priority == "critical"


def test_step_limit(board):
    traj = run_task(ScriptedBackend([tc("list_users")]), build_server(board), "x", max_steps=15)
    assert traj.stop_reason == "max_steps"
    assert traj.steps == 15
    assert len(traj.tool_calls) == 15
    assert traj.final_answer == ""


def test_trajectory_record(board):
    backend = ScriptedBackend([tc("get_issue", key="WEB-2"), "OK"])
    traj = run_task(backend, build_server(board), "Pokaż WEB-2.", task_id="t9")
    assert set(Trajectory.model_fields) >= {
        "messages", "tool_calls", "final_answer", "stop_reason", "steps", "invalid_calls",
        "input_tokens", "output_tokens", "time_s", "prompt_version",
    }
    assert traj.task_id == "t9" and traj.prompt_version == PROMPT_VERSION
    assert [m["role"] for m in traj.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert traj.messages[0]["content"] == SYSTEM_PROMPT
    record = traj.tool_calls[0]
    assert record.name == "get_issue" and record.arguments == {"key": "WEB-2"}
    assert json.loads(record.result)["key"] == "WEB-2"
    assert traj.input_tokens > 0 and traj.output_tokens > 0 and traj.time_s >= 0


def test_same_trajectory_twice(board):
    outputs = [tc("search_issues", type="bug"), "Gotowe."]
    a = run_task(ScriptedBackend(outputs), build_server(board.copy_board()), "x")
    b = run_task(ScriptedBackend(outputs), build_server(board.copy_board()), "x")
    assert a.model_dump(exclude={"time_s"}) == b.model_dump(exclude={"time_s"})


def test_tool_error_is_not_invalid(board):
    traj = run_task(ScriptedBackend([tc("get_issue", key="WEB-999"), "ODMOWA: brak"]), build_server(board), "x")
    assert traj.tool_calls[0].is_error and "WEB-999" in traj.tool_calls[0].result
    assert traj.invalid_calls == 0 and traj.tool_errors == 1


def test_exception_in_model(board):
    traj = run_task(ScriptedBackend([RuntimeError("out of memory")]), build_server(board), "x")
    assert traj.stop_reason == "error" and "out of memory" in traj.error


# Parser

def test_parse_correct_call():
    text, calls = parse_output('Szukam.\n<tool_call>\n{"name": "get_issue", "arguments": {"key": "WEB-1"}}\n</tool_call>', 1)
    assert text == "Szukam."
    assert len(calls) == 1 and calls[0].name == "get_issue" and calls[0].arguments == {"key": "WEB-1"}
    assert calls[0].error is None


def test_parse_two_calls_and_think():
    text, calls = parse_output("<think>\nhmm\n</think>\n" + tc("list_users") + "\n" + tc("list_sprints"), 3)
    assert text == ""
    assert [c.name for c in calls] == ["list_users", "list_sprints"]
    assert calls[0].id != calls[1].id


def test_parse_broken_json():
    _, calls = parse_output('<tool_call>{"name": "get_issue", "arguments": {"key": </tool_call>', 1)
    assert len(calls) == 1 and calls[0].error and "JSON" in calls[0].error


def test_parse_arguments_as_string():
    _, calls = parse_output('<tool_call>{"name": "get_issue", "arguments": "{\\"key\\": \\"WEB-1\\"}"}</tool_call>', 1)
    assert calls[0].arguments == {"key": "WEB-1"}


def test_broken_json_in_loop(board):
    backend = ScriptedBackend(['<tool_call>{"name": "get_issue", "arguments": {</tool_call>', "Koniec."])
    traj = run_task(backend, build_server(board), "x")
    assert traj.invalid_calls == 1
    assert traj.messages[3]["role"] == "tool" and traj.messages[3]["content"].startswith("Error:")
    assert traj.final_answer == "Koniec."


def test_unknown_tool_in_loop(board):
    traj = run_task(ScriptedBackend([tc("delete_issue", key="WEB-1"), "ODMOWA: nie"]), build_server(board), "x")
    assert traj.invalid_calls == 1
    assert "unknown tool" in traj.tool_calls[0].result and "update_issue" in traj.tool_calls[0].result


def test_tool_schema(board):
    tools = tools_of(board)
    update = next(t for t in tools if t["function"]["name"] == "update_issue")["function"]
    assert update["parameters"]["required"] == ["key"]
    assert update["parameters"]["properties"]["status"]["enum"] == ["to_do", "in_progress", "done"]
    assert "title" not in update["parameters"]["properties"]["status"]


# Transformers backend

def test_chat_template_has_tools(board):
    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
    except Exception as e:  # noqa: BLE001  No network and no local cache.
        pytest.skip(f"the Hub is not available: {e}")
    tools = tools_of(board)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "Przypisz WEB-1 Ani."},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "list_users", "arguments": {}}}]},
                {"role": "tool", "tool_call_id": "c1", "name": "list_users", "content": '{"users": []}'}]
    prompt = render_prompt(tokenizer, messages, tools, enable_thinking=False)
    for name in ("list_users", "search_issues", "update_issue", "add_comment"):
        assert f'"name": "{name}"' in prompt
    assert "<tools>" in prompt and "<tool_response>" in prompt
    assert prompt.rstrip().endswith("</think>")  # The thinking mode is off.
    assert tokenizer.decode(tokenizer("<tool_call>x</tool_call>")["input_ids"], skip_special_tokens=True) == "<tool_call>x</tool_call>"


# OpenAI backend

class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def response(content=None, tool_calls=()):
    calls = [SimpleNamespace(id=f"id{n}", function=SimpleNamespace(name=name, arguments=args))
             for n, (name, args) in enumerate(tool_calls)]
    message = SimpleNamespace(content=content, tool_calls=calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10))


def test_openai_backend(board):
    client = FakeClient([
        response(tool_calls=[("update_issue", '{"key": "WEB-1", "assignee": "u2"}'), ("get_issue", "{bad")]),
        response(content="Gotowe."),
    ])
    backend = OpenAIBackend("gpt-test", client=client)
    traj = run_task(backend, build_server(board), "Daj WEB-1 komuś.")
    assert traj.final_answer == "Gotowe."
    assert board.issue("WEB-1").assignee == "u2"
    assert traj.invalid_calls == 1
    assert traj.input_tokens == 200 and traj.output_tokens == 20
    first, second = client.requests
    assert first["model"] == "gpt-test" and first["temperature"] == 0
    assert first["tools"][0]["type"] == "function"
    sent = second["messages"]
    assert sent[2]["role"] == "assistant"
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == '{"key": "WEB-1", "assignee": "u2"}'
    assert sent[2]["tool_calls"][1]["function"]["arguments"] == "{bad"
    assert sent[3] == {"role": "tool", "tool_call_id": "id0", "content": sent[3]["content"]}
    assert json.loads(sent[3]["content"])["assignee"] == "u2"
    assert sent[4]["tool_call_id"] == "id1" and sent[4]["content"].startswith("Error:")


def test_openai_key_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-123")
    backend = OpenAIBackend("m", base_url="http://localhost:1/v1", api_key_env="TEST_API_KEY")
    assert backend.client.api_key == "secret-123"
