import json
import shutil
from pathlib import Path

import pytest

from src.evaluate import load_config, merge, run_evaluation
from src.models import FAMILIES, ScriptedModel
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
    assert not is_garbled("") and not is_garbled("Zmieniono APP-24 na Highest.")


def test_select_task_ids(ten_tasks, data_dir, tmp_path):
    ids = [ten_tasks[1].id, ten_tasks[4].id]
    cfg = {**config(), "tasks": {"split": "test", "limit": None, "ids": ids}}
    metrics = run_evaluation(cfg, tmp_path / "out", model=reference_model(ten_tasks), data_dir=data_dir)
    assert metrics["n"] == 2
    assert [r["task_id"] for r in read_jsonl(tmp_path / "out" / "results.jsonl")] == ids
