import json
from types import SimpleNamespace

import pytest

from src.models import (
    FAMILIES,
    ApiModel,
    LocalModel,
    ScriptedModel,
    check_config,
    load_prompt,
    make_model,
)
from src.tools import TOOL_DEFS

TOOLS = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                            "parameters": t["inputSchema"]}} for t in TOOL_DEFS]
CALL_A = {"name": "jira_get_issue", "arguments": {"issue_key": "WEB-6", "comment_limit": 5}}
CALL_B = {"name": "jira_update_issue",
          "arguments": {"issue_key": "WEB-7", "fields": '{"assignee": "Ewa Mazur", "priority": {"name": "High"}}'}}

# Example outputs of each family, in the formats of the chat templates.
EXAMPLES = {
    "qwen3.5": {
        "one": "<tool_call>\n<function=jira_get_issue>\n<parameter=issue_key>\nWEB-6\n</parameter>\n"
               "<parameter=comment_limit>\n5\n</parameter>\n</function>\n</tool_call>",
        "broken": "<tool_call>\n<function=jira_get_issue>\n<parameter=comment_limit>\nfive\n</parameter>\n</function>\n</tool_call>",
        "thinking": "Muszę sprawdzić WEB-6.\n</think>\n\n<tool_call>\n<function=jira_get_issue>\n"
                    "<parameter=issue_key>\nWEB-6\n</parameter>\n<parameter=comment_limit>\n5\n</parameter>\n</function>\n</tool_call>",
    },
    "gemma4": {
        "one": '<|tool_call>call:jira_get_issue{comment_limit:5,issue_key:<|"|>WEB-6<|"|>}<tool_call|>',
        "broken": '<|tool_call>call:jira_get_issue{issue_key:<|"|>WEB-6}<tool_call|>',
        "thinking": '<|channel>thought\nMuszę sprawdzić WEB-6.<channel|>'
                    '<|tool_call>call:jira_get_issue{comment_limit:5,issue_key:<|"|>WEB-6<|"|>}<tool_call|>',
    },
    "bielik": {
        "one": '<tool_call>{"name": "jira_get_issue", "arguments": {"issue_key": "WEB-6", "comment_limit": 5}}</tool_call>',
        "broken": '<tool_call>{"name": "jira_get_issue", "arguments": {"issue_key": "WEB-6",}}</tool_call>',
        "thinking": None,
    },
}


# Parsers

@pytest.mark.parametrize("family", FAMILIES)
def test_one_call(family):
    text, calls, thinking = FAMILIES[family].parse("Sprawdzam.\n" + EXAMPLES[family]["one"], TOOLS)
    assert [(c.name, c.arguments, c.error) for c in calls] == [(CALL_A["name"], CALL_A["arguments"], None)]
    assert text == "Sprawdzam."
    assert thinking == ""


@pytest.mark.parametrize("family", FAMILIES)
def test_two_calls_round_trip(family):
    f = FAMILIES[family]
    _, calls, _ = f.parse(f.format_calls([CALL_A, CALL_B]), TOOLS)
    assert [(c.name, c.arguments) for c in calls] == [(CALL_A["name"], CALL_A["arguments"]),
                                                       (CALL_B["name"], CALL_B["arguments"])]
    assert all(c.error is None for c in calls)


@pytest.mark.parametrize("family", FAMILIES)
def test_broken_arguments(family):
    _, calls, _ = FAMILIES[family].parse(EXAMPLES[family]["broken"], TOOLS)
    assert len(calls) == 1 and calls[0].error and calls[0].arguments is None


@pytest.mark.parametrize("family", FAMILIES)
def test_text_without_call(family):
    assert FAMILIES[family].parse("WEB-6 ma Ewa Mazur.", TOOLS) == ("WEB-6 ma Ewa Mazur.", [], "")


@pytest.mark.parametrize("family", ["qwen3.5", "gemma4"])
def test_thinking_text(family):
    text, calls, thinking = FAMILIES[family].parse(EXAMPLES[family]["thinking"], TOOLS)
    assert thinking == "Muszę sprawdzić WEB-6."
    assert text == "" and calls[0].arguments == CALL_A["arguments"]


def test_qwen_types_from_schema():
    raw = ("<tool_call>\n<function=jira_transition_issue>\n<parameter=issue_key>\nWEB-1\n</parameter>\n"
           "<parameter=transition_id>\n51\n</parameter>\n</function>\n</tool_call>")
    _, calls, _ = FAMILIES["qwen3.5"].parse(raw, TOOLS)
    assert calls[0].arguments == {"issue_key": "WEB-1", "transition_id": "51"}


def test_gemma_nested_values():
    raw = '<|tool_call>call:x{a:{b:[1,<|"|>c, d<|"|>,true,null]},e:-2.5}<tool_call|>'
    _, calls, _ = FAMILIES["gemma4"].parse(raw)
    assert calls[0].arguments == {"a": {"b": [1, "c, d", True, None]}, "e": -2.5}


# Bielik prompt

def test_bielik_system_prompt():
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "Pokaż WEB-6."},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "c1", "type": "function", "function": CALL_A}]},
                {"role": "tool", "tool_call_id": "c1", "name": "jira_get_issue", "content": "{}"},
                {"role": "tool", "tool_call_id": "c2", "name": "jira_get_issue", "content": "{}"}]
    prepared, tools = FAMILIES["bielik"].prepare(messages, TOOLS)
    system = prepared[0]["content"]
    assert tools is None
    assert all(t["name"] in system for t in TOOL_DEFS)
    assert "<tool_call>" in system and system.startswith("SYSTEM")
    assert FAMILIES["bielik"].parse(prepared[2]["content"])[1][0].arguments == CALL_A["arguments"]
    assert [m["role"] for m in prepared] == ["system", "user", "assistant", "user"]
    assert prepared[3]["content"].count("<tool_response>") == 2


# Render with the real chat templates (only when the tokenizer files exist)

def cached_tokenizer(repo: str):
    from huggingface_hub import try_to_load_from_cache

    path = try_to_load_from_cache(repo, "tokenizer_config.json")
    if not isinstance(path, str):
        pytest.skip(f"tokenizer of {repo} not in the local cache")
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(repo, local_files_only=True)


@pytest.mark.parametrize("family,repo,turn,think_mark", [
    ("qwen3.5", "Qwen/Qwen3.5-2B", "<|im_start|>assistant\n", "<think>\n"),
    ("gemma4", "google/gemma-4-E2B-it", "<|turn>model\n", "<|think|>"),
])
def test_render_and_parse_with_template(family, repo, turn, think_mark):
    tokenizer = cached_tokenizer(repo)
    f = FAMILIES[family]
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "Pokaż WEB-6."}]
    prompt = f.render(tokenizer, messages, TOOLS, thinking=False)
    assert all(t["name"] in prompt for t in TOOL_DEFS) and "SYSTEM" in prompt
    assert turn in prompt
    thinking_prompt = f.render(tokenizer, messages, TOOLS, thinking=True)
    # Without thinking, Qwen3.5 gets an empty think block, so the open mark is at the end only with thinking.
    assert thinking_prompt.rstrip("\n").endswith("<think>") if family == "qwen3.5" else think_mark in thinking_prompt
    assert not prompt.rstrip("\n").endswith("<think>") and "<|think|>" not in prompt
    # The template writes the calls of an assistant message. The parser must read them back.
    history = messages + [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": CALL_A}, {"id": "c2", "type": "function", "function": CALL_B}]}]
    full = tokenizer.apply_chat_template(history, tools=TOOLS, tokenize=False)
    _, calls, _ = f.parse(f.clean(full.rsplit(turn, 1)[1]), TOOLS)
    assert [(c.name, c.arguments) for c in calls] == [(CALL_A["name"], CALL_A["arguments"]),
                                                       (CALL_B["name"], CALL_B["arguments"])]


# make_model and the backends

def test_make_model_scripted():
    model = make_model({"backend": "scripted", "family": "bielik"}, outputs=["OK"])
    assert isinstance(model, ScriptedModel)
    assert model.generate([{"role": "user", "content": "x"}], TOOLS).text == "OK"
    assert model.describe() == {"backend": "scripted", "family": "bielik", "path": "scripted",
                                "revision": "scripted", "thinking": False}


def test_scripted_order():
    model = ScriptedModel(["a", "b"])
    assert [model.generate([], []).text for _ in range(3)] == ["a", "b", "b"]
    with pytest.raises(RuntimeError):
        ScriptedModel([RuntimeError("x")]).generate([], [])


def test_make_model_transformers(monkeypatch, tmp_path):
    import transformers

    seen = []

    class Fake:
        config = SimpleNamespace(_commit_hash=None)

        def to(self, device):
            return self

        def eval(self):
            return self

    def fake_load(kind):
        def load(path, **kwargs):
            seen.append((kind, str(path), kwargs))
            return Fake()
        return load

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", fake_load("tokenizer"))
    monkeypatch.setattr(transformers.AutoModelForCausalLM, "from_pretrained", fake_load("model"))
    model = make_model({"backend": "transformers", "family": "qwen3.5", "path": str(tmp_path), "revision": "abc",
                        "dtype": "float32", "device": "cpu"})
    assert isinstance(model, LocalModel)
    assert seen[0] == ("tokenizer", str(tmp_path), {"local_files_only": True})
    assert seen[1][2]["local_files_only"] is True
    assert model.describe()["revision"] == "abc"
    seen.clear()
    make_model({"backend": "transformers", "family": "gemma4", "path": "google/gemma-4-E2B-it", "revision": "r1",
                "dtype": "float32", "device": "cpu"})
    assert seen[0] == ("tokenizer", "google/gemma-4-E2B-it", {"revision": "r1"})


def test_make_model_openai():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="jira_get_issue", arguments='{"issue_key": "WEB-6"}'))
        message = SimpleNamespace(content="", tool_calls=[tc])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3))

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = ApiModel("gpt-x", client=client)
    out = model.generate([{"role": "user", "content": "x"}], TOOLS)
    assert out.calls[0].arguments == {"issue_key": "WEB-6"} and out.input_tokens == 10
    assert calls[0]["model"] == "gpt-x" and calls[0]["temperature"] == 0 and "extra_body" not in calls[0]
    assert model.describe()["backend"] == "openai"


def test_unknown_backend_and_family():
    with pytest.raises(ValueError, match="Unknown backend 'vllm'"):
        make_model({"backend": "vllm", "family": "qwen3.5"})
    with pytest.raises(ValueError, match="Unknown model family 'llama'"):
        make_model({"backend": "scripted", "family": "llama"})


# Thinking switch

def test_thinking_default_false():
    assert check_config({"backend": "scripted", "family": "qwen3.5"})["thinking"] is False


def test_thinking_qwen():
    assert make_model({"backend": "scripted", "family": "qwen3.5", "thinking": True}).describe()["thinking"] is True
    assert FAMILIES["qwen3.5"].template_args(True) == {"enable_thinking": True}


def test_thinking_bielik_error():
    with pytest.raises(ValueError, match="'bielik' has no thinking mode"):
        make_model({"backend": "scripted", "family": "bielik", "thinking": True})


# Prompt files

def test_prompt_files():
    prompt = load_prompt("system", "v2")
    assert prompt.version == "v2" and len(prompt.sha256) == 64
    assert "ODMOWA:" in prompt.text and "In Progress" in prompt.text
    with pytest.raises(FileNotFoundError, match="system-v9.md"):
        load_prompt("system", "v9")
    assert "{tools}" in load_prompt("tools-bielik", "v1").text


def test_example_outputs_are_json_safe():
    assert json.dumps(EXAMPLES)


def test_bielik_tool_list_is_compact():
    from src.models import compact_tool

    tool = {"name": "jira_get_issue", "description": "Get an issue. More text.",
            "parameters": {"properties": {"issue_key": {"type": "string", "description": "The key.\nLong text."},
                                          "limit": {"type": "integer", "description": "How many."}},
                           "required": ["issue_key"]}}
    text = compact_tool(tool)
    assert text.splitlines()[0] == "- jira_get_issue(issue_key, limit?): Get an issue."
    assert "    issue_key (string): The key." in text and "Long text" not in text
    assert "{tools}" in load_prompt("tools-bielik", "v2").text
