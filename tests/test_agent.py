import asyncio
import hashlib
import json
import random
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
    traj = run_task(ScriptedModel([tc("jira_get_transitions", issue_key="WEB-1")]), build_server(board), "x",
                    loop_limit=None)
    assert DEFAULT_MAX_STEPS == 25
    assert traj.stop_reason == "max_steps" and traj.steps == 25
    assert len(traj.tool_calls) == 25 and traj.final_answer == ""


def test_trajectory_record(board):
    traj = run_task(ScriptedModel([tc("jira_get_issue", issue_key="WEB-2"), "OK"]), build_server(board),
                    "Pokaż WEB-2.", task_id="t9")
    prompt_file = ROOT / "src" / "prompts" / "system-v3.md"
    assert traj.task_id == "t9" and traj.prompt_version == "v3"
    assert traj.prompt_sha256 == hashlib.sha256(prompt_file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert [m["role"] for m in traj.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert traj.messages[0]["content"] == load_prompt("system", "v3").text
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


def test_loop_ends_the_task(board):
    call = tc("jira_get_issue", issue_key="WEB-1")
    traj = run_task(ScriptedModel([call]), build_server(board), "x")
    assert traj.stop_reason == "loop_same" and traj.steps == 3 and len(traj.tool_calls) == 3


def test_different_calls_are_not_a_loop(board):
    outputs = [tc("jira_get_issue", issue_key="WEB-1"), tc("jira_get_issue", issue_key="WEB-2"),
               tc("jira_get_issue", issue_key="WEB-1"), tc("jira_get_issue", issue_key="WEB-1"), "Koniec."]
    traj = run_task(ScriptedModel(outputs), build_server(board), "x")
    assert traj.stop_reason == "answer" and len(traj.tool_calls) == 4


def test_errors_in_a_row_end_the_task(board):
    outputs = [tc("jira_get_issue", issue_key=f"WEB-{900 + i}") for i in range(10)]
    traj = run_task(ScriptedModel(outputs), build_server(board), "x")
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == 5
    assert all(c.is_error for c in traj.tool_calls)


def test_success_resets_the_error_count(board):
    bad = [tc("jira_get_issue", issue_key=f"WEB-{900 + i}") for i in range(4)]
    outputs = bad + [tc("jira_get_issue", issue_key="WEB-1")] + bad + ["Koniec."]
    traj = run_task(ScriptedModel(outputs), build_server(board), "x")
    assert traj.stop_reason == "answer" and len(traj.tool_calls) == 9


def calls_in_one_output(*calls):
    return QWEN.format_calls([{"name": name, "arguments": arguments} for name, arguments in calls])


def test_step_limit_counts_each_call_in_one_output(board):
    calls = [("jira_get_issue", {"issue_key": f"WEB-{i}"}) for i in range(1, 31)]
    model = ScriptedModel([calls_in_one_output(*calls)])
    traj = run_task(model, build_server(board), "x")
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == DEFAULT_MAX_STEPS and traj.steps == 1


def test_step_limit_counts_calls_over_many_outputs(board):
    outputs = [calls_in_one_output(*[("jira_get_issue", {"issue_key": f"WEB-{i + j}"}) for j in range(10)])
               for i in (1, 11, 21)]
    traj = run_task(ScriptedModel(outputs), build_server(board), "x")
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == DEFAULT_MAX_STEPS and traj.steps == 3


def test_loop_stops_inside_one_output_with_another_last_call(board):
    same = ("jira_search_assignable_users", {"query": "Zosia"})
    model = ScriptedModel([calls_in_one_output(*[same] * 33, ("jira_get_issue", {"issue_key": "WEB-1"}))])
    traj = run_task(model, build_server(board), "x")
    assert traj.stop_reason == "loop_same" and len(traj.tool_calls) == 3 and traj.steps == 1


def test_errors_stop_inside_one_output_with_another_last_call(board):
    errors = [("jira_get_issue", {"issue_key": f"NOPE-{i}"}) for i in range(5)]
    model = ScriptedModel([calls_in_one_output(*errors, ("jira_get_issue", {"issue_key": "WEB-1"}))])
    traj = run_task(model, build_server(board), "x")
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == 5 and traj.steps == 1


def test_call_after_a_limit_does_not_change_the_board(board):
    same = ("jira_get_transitions", {"issue_key": "WEB-1"})
    update = ("jira_update_issue", {"issue_key": "WEB-1", "fields": '{"priority": {"name": "Lowest"}}'})
    before = board.find_issue("WEB-1").priority
    run_task(ScriptedModel([calls_in_one_output(same, same, same, update)]), build_server(board), "x")
    assert board.find_issue("WEB-1").priority == before and before != "Lowest"


# Hard limits. The mock model gives fixed outputs. The board shows which calls really ran.

def comment(i):
    return "jira_add_comment", {"issue_key": "WEB-1", "body": f"note {i}"}


BAD = ("jira_get_issue", {"issue_key": "WEB-999"})
TRUNCATED = "\n<tool_call>\n<function=jira"  # The end of an output at the limit of tokens, as in the real runs.


def run_limited(board, outputs, **limits):
    model = ScriptedModel(outputs)
    traj = run_task(model, build_server(board), "x", **limits)
    return traj, model


def comments_on_board(board):
    return sum(c.body.startswith("note ") for c in board.find_issue("WEB-1").comments)


@pytest.mark.parametrize("sizes", [[30], [10, 10, 10], [1] * 30, [24, 6], [25, 5], [13, 13, 13], [26]])
def test_max_steps_is_hard_for_each_split_of_the_calls(board, sizes):
    numbers = iter(range(1000))
    outputs = [calls_in_one_output(*[comment(next(numbers)) for _ in range(size)]) for size in sizes]
    traj, _ = run_limited(board, outputs + ["Koniec."])
    assert traj.stop_reason == "max_steps" and traj.final_answer == ""
    assert len(traj.tool_calls) == 25 and comments_on_board(board) == 25


@pytest.mark.parametrize("limit", [1, 2, 7, 25, 40])
def test_max_steps_is_a_variable(board, limit):
    traj, _ = run_limited(board, [calls_in_one_output(*[comment(i) for i in range(60)])], max_steps=limit)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == limit and comments_on_board(board) == limit


def test_max_steps_stops_the_generation(board):
    _, model = run_limited(board, [calls_in_one_output(*[comment(i) for i in range(25)]), "Koniec."])
    assert model.steps == 1


def test_answer_after_24_calls_is_allowed(board):
    traj, _ = run_limited(board, [calls_in_one_output(*[comment(i) for i in range(24)]), "Koniec."])
    assert traj.stop_reason == "answer" and traj.final_answer == "Koniec." and len(traj.tool_calls) == 24


def test_broken_and_unknown_calls_count_as_steps(board):
    broken = "<tool_call>\n<function=jira_get_issue>\n<parameter=comment_limit>\nfive\n</parameter>\n</function>\n</tool_call>"
    unknown = tc("jira_delete_issue", issue_key="WEB-1")
    traj, _ = run_limited(board, [broken, unknown], loop_limit=None, error_limit=None)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == 25 and traj.invalid_calls == 25


def test_two_same_calls_are_allowed_and_the_third_stops(board):
    same = comment(0)
    traj, _ = run_limited(board, [calls_in_one_output(same, same), "Koniec."])
    assert traj.stop_reason == "answer" and comments_on_board(board) == 2
    traj, _ = run_limited(board.copy_board(), [calls_in_one_output(same, same, same, comment(1)), "Koniec."])
    assert traj.stop_reason == "loop_same" and len(traj.tool_calls) == 3


@pytest.mark.parametrize("sizes", [[3], [1, 2], [2, 1], [1, 1, 1]])
def test_loop_counts_over_outputs(board, sizes):
    same = comment(0)
    outputs = [calls_in_one_output(*[same] * size) for size in sizes] + ["Koniec."]
    traj, model = run_limited(board, outputs)
    assert traj.stop_reason == "loop_same" and comments_on_board(board) == 3 and model.steps == len(sizes)


def test_same_tool_with_other_arguments_is_not_a_loop(board):
    traj, _ = run_limited(board, [calls_in_one_output(*[comment(i) for i in range(10)]), "Koniec."])
    assert traj.stop_reason == "answer" and comments_on_board(board) == 10


@pytest.mark.parametrize("limit", [2, 3, 4, 8])
def test_loop_limit_is_a_variable(board, limit):
    traj, _ = run_limited(board, [calls_in_one_output(*[comment(0)] * 20)], loop_limit=limit)
    assert traj.stop_reason == "loop_same" and comments_on_board(board) == limit


def test_loop_limit_can_be_off(board):
    traj, _ = run_limited(board, [calls_in_one_output(*[comment(0)] * 30)], loop_limit=None)
    assert traj.stop_reason == "max_steps" and comments_on_board(board) == 25


def test_max_steps_stops_a_cycle_that_the_loop_rule_does_not_see(board):
    # A, B, A, B has no equal calls in a row, so only the step limit stops it.
    outputs = [calls_in_one_output(*[comment(i % 2) for i in range(40)])]
    traj, _ = run_limited(board, outputs)
    assert traj.stop_reason == "max_steps" and comments_on_board(board) == 25


def test_four_errors_are_allowed_and_the_fifth_stops(board):
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(5)]
    traj, _ = run_limited(board, [calls_in_one_output(*bad[:4]), "Koniec."])
    assert traj.stop_reason == "answer" and len(traj.tool_calls) == 4
    traj, _ = run_limited(board, [calls_in_one_output(*bad, comment(0)), "Koniec."])
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == 5 and comments_on_board(board) == 0


def test_errors_count_over_outputs(board):
    outputs = [calls_in_one_output(*[("jira_get_issue", {"issue_key": f"WEB-{900 + i + j}"}) for j in range(2)])
               for i in (0, 2, 4)]
    traj, model = run_limited(board, outputs)
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == 5 and model.steps == 3


def test_a_call_that_works_resets_the_errors_inside_one_output(board):
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(4)]
    bad2 = [("jira_get_issue", {"issue_key": f"WEB-{910 + i}"}) for i in range(4)]
    traj, _ = run_limited(board, [calls_in_one_output(*bad, comment(0), *bad2), "Koniec."])
    assert traj.stop_reason == "answer" and len(traj.tool_calls) == 9


def test_each_kind_of_error_counts_in_a_row(board):
    kinds = [BAD, ("jira_delete_issue", {"issue_key": "WEB-1"}), ("jira_get_issue", {"issue_key": "WEB-998"}),
             ("jira_delete_issue", {"issue_key": "WEB-2"}), ("jira_get_issue", {"issue_key": "WEB-997"}), comment(0)]
    traj, _ = run_limited(board, [calls_in_one_output(*kinds)])
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == 5 and comments_on_board(board) == 0


@pytest.mark.parametrize("limit", [1, 2, 7])
def test_error_limit_is_a_variable(board, limit):
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(20)]
    traj, _ = run_limited(board, [calls_in_one_output(*bad)], error_limit=limit)
    assert traj.stop_reason == "loop_errors" and len(traj.tool_calls) == limit


def test_error_limit_can_be_off(board):
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(30)]
    traj, _ = run_limited(board, [calls_in_one_output(*bad)], error_limit=None)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == 25


@pytest.mark.parametrize("name, arguments, count", [
    ("jira_search_assignable_users", {"query": "Zosia"}, 33),  # test-031
    ("jira_search", {"jql": "project = DT AND sprint = null", "limit": 50}, 22),  # test-065
    ("jira_search", {"jql": "project = ZWROT", "limit": 20}, 23),  # test-159
])
def test_outputs_of_the_runs_that_filled_the_memory(board, name, arguments, count):
    output = calls_in_one_output(*[(name, arguments)] * count) + TRUNCATED
    traj, model = run_limited(board, [output])
    assert traj.stop_reason == "loop_same" and len(traj.tool_calls) == 3 and model.steps == 1


def test_many_outputs_with_another_last_call_stop_at_the_step_limit(board):
    # In each output the last call is different, with the loop rule off. This is the old path to 395 calls.
    same = ("jira_search_assignable_users", {"query": "Zosia"})
    traj, model = run_limited(board, [calls_in_one_output(*[same] * 33, BAD)], loop_limit=None, error_limit=None)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == 25 and model.steps == 1


@pytest.mark.parametrize("family", FAMILIES)
def test_hard_limits_for_each_family(board, family):
    f = FAMILIES[family]
    def output(calls):
        return f.format_calls([{"name": name, "arguments": arguments} for name, arguments in calls])
    numbers = [comment(i) for i in range(30)]
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(8)]
    cases = [(numbers, 25, "max_steps"), ([comment(0)] * 8, 3, "loop_same"), (bad, 5, "loop_errors")]
    for calls, count, reason in cases:
        model = ScriptedModel([output(calls)], family=family)
        traj = run_task(model, build_server(board.copy_board()), "x")
        assert traj.stop_reason == reason and len(traj.tool_calls) == count


@pytest.mark.parametrize("seed", range(300))
def test_limits_hold_for_random_outputs(board, seed):
    rng = random.Random(seed)
    pool = [comment(0), comment(1), comment(2), BAD, ("jira_get_issue", {"issue_key": "WEB-998"}),
            ("jira_get_issue", {"issue_key": "WEB-2"}), ("jira_delete_issue", {"issue_key": "WEB-1"})]
    max_steps, loop_limit, error_limit = rng.randint(1, 30), rng.randint(2, 5), rng.randint(2, 6)
    outputs = [calls_in_one_output(*[rng.choice(pool[:rng.randint(1, len(pool))]) for _ in range(rng.randint(1, 15))])
               for _ in range(rng.randint(1, 12))] + ["Koniec."]
    planned = [c for text in outputs[:-1] for c in QWEN.parse(text, [], 0)[1]]
    traj, model = run_limited(board, outputs, max_steps=max_steps, loop_limit=loop_limit, error_limit=error_limit)

    # A check that does not use the code of the agent: walk the records and find the first call over a limit.
    done = traj.tool_calls
    assert len(done) <= max_steps
    assert model.steps <= max_steps + 1
    assert [c.name for c in done] == [c.name for c in planned[:len(done)]]
    streak, errors, last = 0, 0, None
    for position, call in enumerate(done, 1):
        key = (call.name, json.dumps(call.arguments, sort_keys=True))
        streak = streak + 1 if key == last else 1
        last = key
        errors = errors + 1 if call.is_error else 0
        over = streak >= loop_limit or errors >= error_limit or position >= max_steps
        assert not over or position == len(done), f"call {position} of {len(done)} is after a limit"
    if traj.stop_reason == "loop_same":
        assert streak >= loop_limit
    elif traj.stop_reason == "loop_errors":
        assert errors >= error_limit and streak < loop_limit
    elif traj.stop_reason == "max_steps":
        assert len(done) == max_steps
    else:
        assert traj.stop_reason == "answer" and len(done) == len(planned)


def test_both_limits_on_one_call_give_loop_same(board):
    # Five errors that end with three equal calls. The order of the checks must give one fixed reason.
    calls = [("jira_get_issue", {"issue_key": "WEB-901"}), ("jira_get_issue", {"issue_key": "WEB-902"}), BAD, BAD, BAD]
    traj, _ = run_limited(board, [calls_in_one_output(*calls)])
    assert traj.stop_reason == "loop_same" and len(traj.tool_calls) == 5


def test_a_limit_on_the_last_step_gives_the_reason_of_this_limit(board):
    same = comment(0)
    traj, _ = run_limited(board, [calls_in_one_output(comment(1), same, same, same)], max_steps=4)
    assert traj.stop_reason == "loop_same" and len(traj.tool_calls) == 4


@pytest.mark.parametrize("family, broken", [
    ("qwen3.5", "<tool_call>\n<function=jira_get_issue>\n<parameter=comment_limit>\nfive\n</parameter>\n</function>\n</tool_call>"),
    ("gemma4", "<|tool_call>call:jira_get_issue{comment_limit:<|\"|>five<|\"|>}<tool_call|>"),
    ("bielik", '<tool_call>\n{"name": "jira_get_issue", "arguments": {broken\n</tool_call>'),
])
def test_broken_calls_count_as_steps_for_each_family(board, family, broken):
    assert family in FAMILIES
    model = ScriptedModel([broken * 30], family=family)
    traj = run_task(model, build_server(board), "x", loop_limit=None, error_limit=None)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == 25 and traj.steps == 1


@pytest.mark.parametrize("family", FAMILIES)
def test_unknown_tools_count_as_steps_for_each_family(board, family):
    f = FAMILIES[family]
    calls = [{"name": "jira_delete_issue", "arguments": {"issue_key": f"WEB-{i}"}} for i in range(1, 31)]
    traj = run_task(ScriptedModel([f.format_calls(calls)], family=family), build_server(board), "x",
                    loop_limit=None, error_limit=None)
    assert traj.stop_reason == "max_steps" and len(traj.tool_calls) == 25 and traj.invalid_calls == 25
