import json
import re
import shutil
from pathlib import Path

import pytest

from src.evaluate import COMMENT_PLACEHOLDER, fill_report, load_config, main, merge, run_evaluation
from src.models import FAMILIES, ModelStopped, ScriptedModel
from src.tasks import load_tasks, split_dir

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
QWEN = FAMILIES["qwen3.5"]


@pytest.fixture(scope="module")
def ten_tasks():
    """The first task of each category, and the last bulk and workflow tasks (board test-ops)."""
    tasks = load_tasks("test")
    chosen = {t.category: t for t in reversed(tasks)}
    chosen = list(chosen.values()) + [next(t for t in reversed(tasks) if t.category == c) for c in ("bulk", "workflow")]
    return sorted(chosen, key=lambda t: t.id)


@pytest.fixture
def data_dir(tmp_path, ten_tasks):
    """A copy of the data with only the ten tasks in the test split."""
    shutil.copytree(DATA / "environments", tmp_path / "environments")
    folder = tmp_path / "tasks" / "test"
    folder.mkdir(parents=True)
    ids = {t.id for t in ten_tasks}
    for name in ("queries.json", "solutions.json", "expected.json"):
        rows = json.loads((split_dir("test") / name).read_text(encoding="utf-8"))
        (folder / name).write_text(json.dumps([r for r in rows if r["id"] in ids], ensure_ascii=False), encoding="utf-8")
    shutil.copy(split_dir("test") / "personas.json", folder / "personas.json")
    return tmp_path


def reference_model(tasks):
    """A scripted model that does the reference calls of the task, one call in each step, then gives the answer."""
    by_instruction = {t.instruction: t for t in tasks}

    def output(messages, step):
        task = by_instruction[messages[1]["content"]]
        done = sum(m["role"] == "assistant" for m in messages)
        if done < len(task.calls):
            return QWEN.format_calls([task.calls[done].model_dump()])
        return task.reference_answer
    return ScriptedModel(output)


def config():
    return {"codename": "smoke", "model": {"backend": "scripted", "family": "qwen3.5"},
            "agent": {"prompt": "v2", "max_steps": 25}, "tasks": {"split": "test", "limit": None}}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_reference_calls_get_reference_grade(ten_tasks, data_dir, tmp_path):
    metrics = run_evaluation(config(), tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    results = read_jsonl(tmp_path / "out" / "results.jsonl")
    assert [r["task_id"] for r in results] == [t.id for t in ten_tasks]
    for r, t in zip(results, ten_tasks):
        want = "correct_refusal" if t.category == "refusal" else "correct"
        assert r["grade"] == want, (r["task_id"], r["reason"])
        assert r["author"] == t.author and r["board"] == t.board
    assert metrics["score"] == 1.0 and metrics["n"] == 10
    run = metrics["run"]
    assert run["model"] == {"backend": "scripted", "family": "qwen3.5", "path": "scripted", "revision": "scripted",
                            "thinking": False}
    assert run["prompt_version"] == "v2" and len(run["prompt_sha256"]) == 64
    assert run["config"]["model"]["thinking"] is False
    trajectories = read_jsonl(tmp_path / "out" / "trajectories.jsonl")
    assert trajectories[0]["prompt_version"] == "v2"


def test_shards_and_merge(ten_tasks, data_dir, tmp_path):
    for i in range(2):
        run_evaluation(config(), tmp_path / f"s{i}", shard=(i, 2), model=reference_model(ten_tasks), data_dir=data_dir)
    sizes = [len(read_jsonl(tmp_path / f"s{i}" / "results.jsonl")) for i in range(2)]
    assert sizes == [5, 5]
    metrics = merge([tmp_path / "s0", tmp_path / "s1"], tmp_path / "all")
    assert metrics["n"] == 10 and metrics["score"] == 1.0
    assert metrics["run"]["shards"] == ["0/2", "1/2"]
    assert sorted(r["task_id"] for r in read_jsonl(tmp_path / "all" / "results.jsonl")) == sorted(t.id for t in ten_tasks)
    with pytest.raises(ValueError, match="more than one shard"):
        merge([tmp_path / "s0", tmp_path / "s0"], tmp_path / "bad")


def test_error_in_one_task(ten_tasks, data_dir, tmp_path):
    def output(messages, step):
        if step == 1:
            raise RuntimeError("out of memory")
        return "ODMOWA: nie."
    metrics = run_evaluation(config(), tmp_path / "out", model=ScriptedModel(output), data_dir=data_dir)
    results = read_jsonl(tmp_path / "out" / "results.jsonl")
    assert results[0]["grade"] == "incorrect" and "out of memory" in results[0]["reason"]
    assert len(results) == 10 and metrics["errors"] == 1


def test_stop_before_first_task(data_dir, tmp_path):
    cfg = config()
    cfg["agent"]["prompt"] = "v9"
    with pytest.raises(FileNotFoundError, match="system-v9.md"):
        run_evaluation(cfg, tmp_path / "out", data_dir=data_dir)
    cfg = config()
    cfg["model"] = {"backend": "scripted", "family": "bielik", "thinking": True}
    with pytest.raises(ValueError, match="bielik"):
        run_evaluation(cfg, tmp_path / "out", data_dir=data_dir)
    assert not (tmp_path / "out" / "results.jsonl").exists()


def test_missing_train_split(tmp_path):
    metrics = run_evaluation({**config(), "tasks": {"split": "train"}}, tmp_path / "out",
                             model=ScriptedModel(["OK"]), data_dir=tmp_path)
    assert metrics["n"] == 0


def test_load_config(tmp_path):
    (tmp_path / "2026-11-10_01_x").mkdir()
    (tmp_path / "2026-11-10_01_x" / "x.yaml").write_text("model:\n  backend: scripted\n", encoding="utf-8")
    assert load_config("x", tmp_path)["codename"] == "x"
    with pytest.raises(FileNotFoundError):
        load_config("y", tmp_path)


def test_health_and_report(ten_tasks, data_dir, tmp_path):
    metrics = run_evaluation(config(), tmp_path / "out", model=ScriptedModel(["!!!!!!!!!!!!"] * 10), data_dir=data_dir)
    health = metrics["health"]
    assert health["garbled_tasks"] == 10 and health["no_tool_call_tasks"] == 10 and health["empty_answers"] == 0
    report = (tmp_path / "out" / "report-smoke.md").read_text(encoding="utf-8")
    assert "| Task | Category | Instruction |" in report and report.count("\n| test-") == 10


def test_report_after_merge(ten_tasks, data_dir, tmp_path):
    for i in range(2):
        run_evaluation(config(), tmp_path / f"s{i}", shard=(i, 2), model=reference_model(ten_tasks), data_dir=data_dir)
    merge([tmp_path / "s0", tmp_path / "s1"], tmp_path / "all")
    report = (tmp_path / "all" / "report-smoke.md").read_text(encoding="utf-8")
    assert report.count("\n| test-") == 10 and report.count("| 1 |\n") == 10
    assert not any("�" in line for line in report.splitlines())


def test_is_garbled():
    from src.evaluate import is_garbled
    assert is_garbled("!!!!!!!!") and is_garbled("ab �")
    assert not is_garbled("") and not is_garbled("Zmieniono APP-24 na Highest.") and not is_garbled('<|"|>')


def test_select_task_ids(ten_tasks, data_dir, tmp_path):
    ids = [ten_tasks[1].id, ten_tasks[4].id]
    cfg = {**config(), "tasks": {"split": "test", "limit": None, "ids": ids}}
    metrics = run_evaluation(cfg, tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    assert metrics["n"] == 2
    assert [r["task_id"] for r in read_jsonl(tmp_path / "out" / "results.jsonl")] == ids


def test_failed_task_frees_the_memory_of_the_model(data_dir, tmp_path):
    class FailingModel(ScriptedModel):
        freed = 0

        def generate(self, messages, tools):
            raise RuntimeError("out of memory")

        def free_memory(self):
            FailingModel.freed += 1

    metrics = run_evaluation(config(), tmp_path / "out", model=FailingModel([]), data_dir=data_dir)
    assert metrics["errors"] == metrics["n"] == FailingModel.freed


def many_calls(*calls):
    return QWEN.format_calls([{"name": name, "arguments": arguments} for name, arguments in calls])


@pytest.mark.parametrize("agent, count, reason", [
    ({"max_steps": 4, "loop_limit": None, "error_limit": None}, 4, "max_steps"),
    ({"max_steps": 25, "loop_limit": 2, "error_limit": None}, 2, "loop_same"),
    ({"max_steps": 25, "loop_limit": 3}, 3, "loop_same"),
    ({}, 3, "loop_same"),
])
def test_limits_of_the_config_reach_the_agent(ten_tasks, data_dir, tmp_path, agent, count, reason):
    same = ("jira_search", {"jql": "project = WEB", "limit": 1})
    cfg = {**config(), "agent": {"prompt": "v2", **agent}}
    metrics = run_evaluation(cfg, tmp_path / "out", model=ScriptedModel([many_calls(*[same] * 40)]), data_dir=data_dir)
    results = read_jsonl(tmp_path / "out" / "results.jsonl")
    assert len(results) == 10
    assert all(r["tool_calls"] == count and r["stop_reason"] == reason for r in results)
    assert metrics["health"]["max_steps_tasks"] == (10 if reason == "max_steps" else 0)
    assert metrics["health"]["loop_same_tasks"] == (10 if reason == "loop_same" else 0)
    assert metrics["health"]["loop_errors_tasks"] == 0
    trajectories = read_jsonl(tmp_path / "out" / "trajectories.jsonl")
    assert all(len(t["tool_calls"]) == count for t in trajectories)


def test_default_max_steps_of_the_config_is_25(ten_tasks, data_dir, tmp_path):
    calls = [("jira_search", {"jql": f"project = WEB AND summary ~ w{i}", "limit": 1}) for i in range(40)]
    cfg = {**config(), "agent": {"prompt": "v2", "loop_limit": None, "error_limit": None}}
    run_evaluation(cfg, tmp_path / "out", model=ScriptedModel([many_calls(*calls)]), data_dir=data_dir)
    assert all(r["tool_calls"] == 25 and r["stop_reason"] == "max_steps"
               for r in read_jsonl(tmp_path / "out" / "results.jsonl"))


def test_metrics_count_each_kind_of_loop(ten_tasks, data_dir, tmp_path):
    bad = [("jira_get_issue", {"issue_key": f"WEB-{900 + i}"}) for i in range(8)]
    metrics = run_evaluation(config(), tmp_path / "out", model=ScriptedModel([many_calls(*bad)]), data_dir=data_dir)
    assert metrics["health"]["loop_errors_tasks"] == 10 and metrics["health"]["loop_same_tasks"] == 0
    assert all(r["stop_reason"] == "loop_errors" for r in read_jsonl(tmp_path / "out" / "results.jsonl"))


def test_report_has_the_form_of_agents_md(ten_tasks, data_dir, tmp_path):
    metrics = run_evaluation(config(), tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    report = (tmp_path / "out" / "report-smoke.md").read_text(encoding="utf-8")
    parts = ["# Report of smoke", "Time of the job:", "| Task type | Tasks | Score |", f"| All | 10 | {metrics['score']:.3f} |",
             "| Category | Tasks | Score |", "Health: ", "## What SFT and RL must teach", "## Tasks",
             "| Task | Category | Instruction | Calls | Answer of the model | Reason | Why | Points |"]
    positions = [report.index(part) for part in parts]
    assert positions == sorted(positions)
    rows = [line for line in report.splitlines() if line.startswith("| test-")]
    assert len(rows) == 10 and all(row.endswith("|  | 1 |") for row in rows)


def test_report_writes_only_the_task_types_of_the_run(ten_tasks, data_dir, tmp_path):
    metrics = run_evaluation(config(), tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    report = (tmp_path / "out" / "report-smoke.md").read_text(encoding="utf-8")
    types = [line.split("`")[1] for line in report.splitlines() if line.startswith("| `")]
    assert types == [k for k in ("easy", "multi_step", "refusal") if k in metrics["by_difficulty"]]


def _unfilled_report(tasks, data_dir, tmp_path):
    run_evaluation(config(), tmp_path / "out", model=reference_model(tasks), data_dir=data_dir)
    (tmp_path / "why.txt").write_text("".join(f"{t.id} Did the step {i}.\n" for i, t in enumerate(tasks)), encoding="utf-8")
    (tmp_path / "comment.md").write_text("- Teach the correct key.\n- Teach the refusal.\n", encoding="utf-8")
    return tmp_path / "out" / "report-smoke.md", tmp_path / "why.txt", tmp_path / "comment.md", tmp_path / "final" / "report.md"


def test_fill_report_puts_the_cells_into_the_rows(ten_tasks, data_dir, tmp_path):
    paths = _unfilled_report(ten_tasks, data_dir, tmp_path)
    fill_report(*paths)
    report = paths[3].read_text(encoding="utf-8")
    assert "- Teach the correct key.\n- Teach the refusal.\n\n## Tasks" in report and COMMENT_PLACEHOLDER not in report
    for i, t in enumerate(ten_tasks):
        row = next(line for line in report.splitlines() if line.startswith(f"| {t.id} |"))
        assert row.endswith(f"| Did the step {i}. | 1 |")


@pytest.mark.parametrize("why, comment, problem", [
    (lambda w: w.rsplit("\n", 2)[0] + "\n", None, "differ from the report"),
    (lambda w: w + "test-999 Extra task.\n", None, "differ from the report"),
    (lambda w: w.replace("Did", "Did |", 1), None, "has |"),
    (lambda w: w.replace("Did the step 0.", ""), None, "empty"),
    (lambda w: w.replace("Did the step 0.", "word " * 26), None, "more than 25 words"),
    (lambda w: re.sub(r"step \d", "step", w), None, "equal Why cells"),
    (None, "- line\n" * 7, "1 to 6 lines"),
    (None, "no dash\n", "1 to 6 lines"),
    (None, "", "1 to 6 lines"),
    (None, "- " + "word " * 41, "more than 40 words"),
    (None, "- test-001 test-002 test-003 test-004\n", "more than 3 task ids"),
])
def test_fill_report_stops_on_each_problem(ten_tasks, data_dir, tmp_path, why, comment, problem):
    paths = _unfilled_report(ten_tasks, data_dir, tmp_path)
    if why:
        paths[1].write_text(why(paths[1].read_text(encoding="utf-8")), encoding="utf-8")
    if comment is not None:
        paths[2].write_text(comment, encoding="utf-8")
    with pytest.raises(ValueError, match=problem):
        fill_report(*paths)
    assert not paths[3].exists()


def test_fill_report_does_not_fill_a_report_two_times(ten_tasks, data_dir, tmp_path):
    report, why, comment, output = _unfilled_report(ten_tasks, data_dir, tmp_path)
    fill_report(report, why, comment, output)
    with pytest.raises(ValueError, match="not an unfilled report"):
        fill_report(output, why, comment, tmp_path / "again.md")


def test_fill_from_the_command_line(ten_tasks, data_dir, tmp_path):
    report, why, comment, output = _unfilled_report(ten_tasks, data_dir, tmp_path)
    main(["--fill", str(report), "--why", str(why), "--comment", str(comment), "--output", str(output)])
    assert output.exists()
    with pytest.raises(SystemExit):
        main(["--fill", str(report), "--output", str(output)])


def test_stopped_model_keeps_results_and_resume_does_the_rest(ten_tasks, data_dir, tmp_path):
    good = reference_model(ten_tasks)
    answers = {"count": 0}

    def stops_after_three_tasks(messages, step):
        if messages[-1]["role"] == "user":
            answers["count"] += 1
        if answers["count"] > 3:
            raise ModelStopped("limit")
        return good.outputs(messages, step)

    with pytest.raises(ModelStopped):
        run_evaluation(config(), tmp_path / "out", model=ScriptedModel(stops_after_three_tasks), data_dir=data_dir)
    assert len(read_jsonl(tmp_path / "out" / "results.jsonl")) == 3

    metrics = run_evaluation(config(), tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir, resume=True)
    results = read_jsonl(tmp_path / "out" / "results.jsonl")
    assert metrics["n"] == len(ten_tasks) == len(results)
    assert len({r["task_id"] for r in results}) == len(results)
    assert len(read_jsonl(tmp_path / "out" / "trajectories.jsonl")) == len(results)


def test_reference_report_has_no_why_and_has_cost(ten_tasks, data_dir, tmp_path):
    run_evaluation(config(), tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    main(["--reference-report", str(tmp_path / "out")])
    text = (tmp_path / "out" / "report-smoke.md").read_text(encoding="utf-8")
    assert "Why" not in text and "What SFT and RL" not in text and "Cost: 0.00 USD" in text
    assert "| Reason | Points |" in text
