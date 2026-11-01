import json

import pytest

from src.agent import ScriptedBackend
from src.evaluate import (
    compute_metrics,
    evaluate_task,
    load_config,
    main,
    merge,
    run_evaluation,
)
from src.tasks import load_tasks

CONFIG = {"model": {"backend": "scripted"}, "agent": {"max_steps": 15}, "tasks": {"split": "test", "limit": None},
          "codename": "test-v1"}


def oracle(fail_on: str | None = None):
    """A scripted model that does the reference solution of each test task, and fails on one instruction."""
    tasks = {t.instruction: t for t in load_tasks("test")}

    def output(messages, step):
        task = tasks[messages[1]["content"]]
        if task.instruction == fail_on:
            return RuntimeError("model failure")
        if step == 1 and task.solution:
            return "".join(f'<tool_call>{json.dumps(c.model_dump())}</tool_call>' for c in task.solution)
        return "ODMOWA: nie mogę tego zrobić." if task.difficulty == "refusal" else "Gotowe."
    return ScriptedBackend(output)


def cfg(limit):
    return {**CONFIG, "tasks": {"split": "test", "limit": limit}}


def test_load_config(tmp_path):
    (tmp_path / "2026-11-01_01_job").mkdir()
    (tmp_path / "2026-11-01_01_job" / "base-v1.yaml").write_text("model:\n  backend: transformers\n")
    assert load_config("base-v1", tmp_path) == {"model": {"backend": "transformers"}, "codename": "base-v1"}
    with pytest.raises(FileNotFoundError, match=r"\[\]"):
        load_config("other", tmp_path)
    (tmp_path / "2026-11-02_01_job").mkdir()
    (tmp_path / "2026-11-02_01_job" / "base-v1.yaml").write_text("model: {}\n")
    with pytest.raises(FileNotFoundError, match="2026-11-02_01_job"):
        load_config("base-v1", tmp_path)


def test_load_config_from_path(tmp_path):
    path = tmp_path / "smoke.yaml"
    path.write_text("tasks:\n  split: test\n")
    assert load_config(str(path))["codename"] == "smoke"


def test_run_three_tasks(tmp_path):
    metrics = run_evaluation(cfg(3), tmp_path, backend=oracle())
    results = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    trajectories = (tmp_path / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(results) == 3 and len(trajectories) == 3
    assert {"task_id", "difficulty", "category", "grade", "reason", "steps", "invalid_calls",
            "input_tokens", "output_tokens", "time_s"} <= set(results[0])
    assert all(r["grade"] in ("correct", "correct_refusal") for r in results), results
    assert metrics["score"] == 1.0
    saved = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    run = saved["run"]
    assert run["codename"] == "test-v1" and run["prompt_version"] == "v1"
    for key in ("config", "model", "model_revision", "git_commit", "python", "torch", "transformers", "device", "date"):
        assert key in run


def test_error_in_one_task(tmp_path):
    tasks = load_tasks("test")[:3]
    run_evaluation(cfg(3), tmp_path, backend=oracle(fail_on=tasks[1].instruction))
    results = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert results[1]["grade"] == "incorrect" and "model failure" in results[1]["reason"]
    assert results[1]["error"]
    assert results[2]["grade"] in ("correct", "correct_refusal")


def test_fresh_board_for_each_task():
    task = next(t for t in load_tasks("test") if t.difficulty == "easy")
    backend = oracle()
    first, _ = evaluate_task(task, backend, 15)
    second, _ = evaluate_task(task, backend, 15)
    assert first["grade"] == second["grade"] == "correct"


def test_shards_and_merge(tmp_path):
    tasks = load_tasks("test")[:7]
    fail = tasks[4].instruction
    run_evaluation(cfg(7), tmp_path / "s0", shard=(0, 2), backend=oracle(fail))
    run_evaluation(cfg(7), tmp_path / "s1", shard=(1, 2), backend=oracle(fail))
    metrics = merge([tmp_path / "s0", tmp_path / "s1"], tmp_path / "all")
    results = [json.loads(line) for line in (tmp_path / "all" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(r["task_id"] for r in results) == sorted(t.id for t in tasks)
    assert len(results) == len({r["task_id"] for r in results}) == 7
    assert metrics["n"] == 7
    assert metrics["score"] == round(6 / 7, 4)
    assert metrics["errors"] == 1
    assert metrics["run"]["shards"] == ["0/2", "1/2"]
    for difficulty, summary in metrics["by_difficulty"].items():
        rows = [r for r in results if r["difficulty"] == difficulty]
        assert summary["n"] == len(rows)
    assert metrics["total_time_s"] == round(sum(r["time_s"] for r in results), 3)


def test_metrics_by_difficulty():
    rows = [
        {"difficulty": "easy", "category": "a", "grade": "correct"},
        {"difficulty": "easy", "category": "a", "grade": "incorrect"},
        {"difficulty": "multi_step", "category": "b", "grade": "correct"},
        {"difficulty": "refusal", "category": "c", "grade": "correct_refusal"},
    ]
    for r in rows:
        r.update(steps=2, invalid_calls=1, tool_errors=0, input_tokens=10, output_tokens=4, time_s=1.0, error=None)
    m = compute_metrics(rows)
    assert m["score"] == 0.75 and m["correct"] == 0.5 and m["correct_refusal"] == 0.25
    assert m["by_difficulty"]["easy"]["score"] == 0.5
    assert set(m["by_difficulty"]) == {"easy", "multi_step", "refusal"}
    assert m["mean_steps"] == 2 and m["total_time_s"] == 4.0


def test_merge_command(tmp_path):
    run_evaluation(cfg(2), tmp_path / "s0", shard=(0, 2), backend=oracle())
    run_evaluation(cfg(2), tmp_path / "s1", shard=(1, 2), backend=oracle())
    main(["--merge", str(tmp_path / "s0"), str(tmp_path / "s1"), "--output", str(tmp_path / "all")])
    assert {p.name for p in (tmp_path / "all").iterdir()} == {"results.jsonl", "trajectories.jsonl", "metrics.json"}
