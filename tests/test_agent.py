import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import mcp
import pytest

from src.agent import DEFAULT_MAX_STEPS, Trajectory, run_task, tool_schema
from src.environment import load_board
from src.models import FAMILIES, ApiModel, ScriptedModel, load_prompt
from src.tools import build_server

ROOT = Path(__file__).resolve().parents[1]
QWEN = FAMILIES["qwen3.5"]


def tc(name, **arguments):
    return QWEN.format_calls([{"name": name, "arguments": arguments}])


@pytest.fixture
def board():
    return load_board(ROOT / "data" / "environments" / "test-web.json")


def test_final_answer(board):
    model = ScriptedModel([tc("jira_update_issue", issue_key="WEB-1", fields='{"priority": {"name": "Highest"}}'),
                           "Gotowe, zmieniłem priorytet."])
    traj = run_task(model, build_server(board), "Ustaw WEB-1 priorytet Highest.", task_id="t1")
    assert traj.stop_reason == "answer"
    assert traj.final_answer == "Gotowe, zmieniłem priorytet."
    assert traj.steps == 2
    assert board.find_issue("WEB-1").priority == "Highest"


def test_step_limit(board):
    traj = run_task(ScriptedModel([tc("jira_get_transitions", issue_key="WEB-1")]), build_server(board), "x")
    assert DEFAULT_MAX_STEPS == 25
    assert traj.stop_reason == "max_steps" and traj.steps == 25
    assert len(traj.tool_calls) == 25 and traj.final_answer == ""


def test_trajectory_record(board):
    traj = run_task(ScriptedModel([tc("jira_get_issue", issue_key="WEB-2"), "OK"]), build_server(board),
                    "Pokaż WEB-2.", task_id="t9")
    prompt_file = ROOT / "src" / "prompts" / "system-v2.md"
    assert traj.task_id == "t9" and traj.prompt_version == "v2"
    assert traj.prompt_sha256 == hashlib.sha256(prompt_file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert [m["role"] for m in traj.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert traj.messages[0]["content"] == load_prompt("system", "v2").text
    record = traj.tool_calls[0]
    assert record.name == "jira_get_issue" and record.arguments == {"issue_key": "WEB-2"}
    assert json.loads(record.result)["key"] == "WEB-2"
    assert traj.input_tokens > 0 and traj.output_tokens > 0 and traj.time_s >= 0


def test_other_prompt_version(board, tmp_path, monkeypatch):
    monkeypatch.setattr("src.models.PROMPTS_DIR", tmp_path)
    (tmp_path / "system-v3.md").write_text("Nowy prompt.", encoding="utf-8")
    traj = run_task(ScriptedModel(["OK"]), build_server(board), "x", prompt=load_prompt("system", "v3"))
    assert traj.prompt_version == "v3" and traj.messages[0]["content"] == "Nowy prompt."


def test_thinking_goes_into_trajectory(board):
    model = ScriptedModel(["Najpierw sprawdzę.\n</think>\n\nWEB-6 ma Ewa Mazur."], thinking=True)
    traj = run_task(model, build_server(board), "x")
    assert traj.final_answer == "WEB-6 ma Ewa Mazur."
    assert traj.thinking == ["Najpierw sprawdzę."]


def test_same_trajectory_twice(board):
    outputs = [tc("jira_search", jql="project = WEB AND type = Bug"), "Gotowe."]
    a = run_task(ScriptedModel(outputs), build_server(board.copy_board()), "x")
    b = run_task(ScriptedModel(outputs), build_server(board.copy_board()), "x")
    assert a.model_dump(exclude={"time_s"}) == b.model_dump(exclude={"time_s"})


def test_tool_error_is_not_invalid(board):
    traj = run_task(ScriptedModel([tc("jira_get_issue", issue_key="WEB-999"), "ODMOWA: brak"]), build_server(board), "x")
    assert traj.tool_calls[0].is_error and "WEB-999" in traj.tool_calls[0].result
    assert traj.invalid_calls == 0 and traj.tool_errors == 1


def test_exception_in_model(board):
    traj = run_task(ScriptedModel([RuntimeError("out of memory")]), build_server(board), "x")
    assert traj.stop_reason == "error" and "out of memory" in traj.error


def test_broken_call_in_loop(board):
    broken = "<tool_call>\n<function=jira_get_issue>\n<parameter=comment_limit>\nfive\n</parameter>\n</function>\n</tool_call>"
    traj = run_task(ScriptedModel([broken, "Koniec."]), build_server(board), "x")
    assert traj.invalid_calls == 1
    assert traj.messages[3]["role"] == "tool" and traj.messages[3]["content"].startswith("Error:")
    assert traj.final_answer == "Koniec."


def test_unknown_tool_in_loop(board):
    traj = run_task(ScriptedModel([tc("jira_delete_issue", issue_key="WEB-1"), "ODMOWA: nie"]), build_server(board), "x")
    assert traj.invalid_calls == 1
    assert "unknown tool" in traj.tool_calls[0].result and "jira_update_issue" in traj.tool_calls[0].result


@pytest.mark.parametrize("family", FAMILIES)
def test_same_loop_for_each_family(board, family):
    f = FAMILIES[family]
    model = ScriptedModel([f.format_calls([{"name": "jira_get_issue", "arguments": {"issue_key": "WEB-6"}}]), "OK"],
                          family=family)
    traj = run_task(model, build_server(board.copy_board()), "x")
    assert traj.tool_calls[0].name == "jira_get_issue" and not traj.tool_calls[0].is_error
    assert traj.final_answer == "OK"


def test_tool_schema(board):
    async def go():
        async with mcp.Client(build_server(board)) as client:
            return [tool_schema(t) for t in (await client.list_tools()).tools]

    tools = asyncio.run(go())
    update = next(t for t in tools if t["function"]["name"] == "jira_update_issue")["function"]
    assert update["parameters"]["required"] == ["issue_key", "fields"]
    assert "default" not in update["parameters"]["properties"]["additional_fields"]
    assert update["parameters"]["properties"]["return_fields"]["default"] == "*all"


# OpenAI backend in the loop

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
        response(tool_calls=[("jira_update_issue", '{"issue_key": "WEB-1", "fields": "{\\"assignee\\": \\"Ewa Mazur\\"}"}'),
                             ("jira_get_issue", "{bad")]),
        response(content="Gotowe."),
    ])
    traj = run_task(ApiModel("gpt-test", client=client), build_server(board), "Daj WEB-1 Ewie.")
    assert traj.final_answer == "Gotowe."
    assert board.display_name(board.find_issue("WEB-1").assignee) == "Ewa Mazur"
    assert traj.invalid_calls == 1
    assert traj.input_tokens == 200 and traj.output_tokens == 20
    first, second = client.requests
    assert first["model"] == "gpt-test" and first["temperature"] == 0
    assert first["tools"][0]["type"] == "function"
    sent = second["messages"]
    assert sent[2]["role"] == "assistant" and sent[2]["tool_calls"][1]["function"]["arguments"] == "{bad"
    assert sent[3]["tool_call_id"] == "id0" and json.loads(sent[3]["content"])["message"] == "Issue updated successfully"
    assert sent[4]["tool_call_id"] == "id1" and sent[4]["content"].startswith("Error:")


def test_openai_key_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-123")
    model = ApiModel("m", base_url="http://localhost:1/v1", api_key_env="TEST_API_KEY")
    assert model.client.api_key == "secret-123"


def test_trajectory_fields():
    assert {"prompt_version", "prompt_sha256", "thinking", "messages", "tool_calls"} <= set(Trajectory.model_fields)


def test_arguments_that_are_not_an_object(board):
    call = '<tool_call>{"name": "jira_get_issue", "arguments": ["WEB-1"]}</tool_call>'
    model = ScriptedModel([call, "ODMOWA: nie."], family="bielik")
    traj = run_task(model, build_server(board), "x")
    assert traj.stop_reason == "answer" and traj.invalid_calls == 1
    assert "must be a JSON object" in traj.tool_calls[0].result
