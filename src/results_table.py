"""Make data/results/baseline/results_baseline.csv from the runs of the baselines.

The file is the one source for all later numbers. The script reads the grade of each
task from `results.jsonl` and checks the numbers against `metrics.json` and the report
of each run. It stops with an error if a check fails.

Usage: python -m src.results_table
"""

import csv
import json
import re
from pathlib import Path

RUNS = Path("jobs/runs")
BASELINE = Path("data/results/baseline")
OUTPUT = BASELINE / "results_baseline.csv"

# Display name, group, folder of the run, report file. One family stays together.
MODELS = [
    ("Haiku 5.5", "external", "2026-11-07_35_kaggle-reference", "baseline-claude-haiku-5-5", "report-out-baseline-claude-haiku-5-5.md"),
    ("Sonnet 5.5", "external", "2026-11-07_35_kaggle-reference", "baseline-claude-sonnet-5-5", "report-out-baseline-claude-sonnet-5-5.md"),
    ("Opus 5.5", "external", "2026-11-07_35_kaggle-reference", "baseline-claude-opus-5-5", "report-out-baseline-claude-opus-5-5.md"),
    ("Gemini 4 Argon", "external", "2026-11-07_35_kaggle-reference", "baseline-gemini-4-argon", "report-out-baseline-gemini-4-argon.md"),
    ("Bielik 1.5B", "local", "2026-11-06_22_baseline-bielik-1-5b-v3-v2", "baseline-bielik-1-5b-v3-v2", "report-baseline-bielik-1-5b-v3-v2.md"),
    ("Bielik 4.5B", "local", "2026-11-06_23_baseline-bielik-4-5b-v3-v2", "baseline-bielik-4-5b-v3-v2", "report-baseline-bielik-4-5b-v3-v2.md"),
    ("Qwen3.5-2B", "local", "2026-11-06_24_baseline-qwen3-5-2b-v2", "baseline-qwen3-5-2b-v2", "report-baseline-qwen3-5-2b-v2.md"),
    ("Qwen3.5-4B", "local", "2026-11-06_25_baseline-qwen3-5-4b-v3", "baseline-qwen3-5-4b-v3", "report-baseline-qwen3-5-4b-v3.md"),
    ("Gemma 4 E2B", "local", "2026-11-06_20_baseline-gemma-4-e2b-v2", "baseline-gemma-4-e2b-v2", "report-baseline-gemma-4-e2b-v2.md"),
    ("Gemma 4 E4B", "local", "2026-11-06_21_baseline-gemma-4-e4b-v2", "baseline-gemma-4-e4b-v2", "report-baseline-gemma-4-e4b-v2.md"),
]
TYPES = ["easy", "multi_step", "refusal"]
CATEGORIES = ["bulk", "create", "log", "query", "refusal", "sprint", "update", "workflow"]
PASS = ("correct", "correct_refusal")
N_TASKS = 200
TYPE_COUNTS = {"easy": 72, "multi_step": 103, "refusal": 25}
CATEGORY_COUNTS = {"bulk": 20, "create": 25, "log": 25, "query": 30,
                   "refusal": 25, "sprint": 25, "update": 30, "workflow": 20}

COLUMNS = (
    ["model", "codename", "group", "tasks", "score_all"]
    + [f"score_{t}" for t in TYPES]
    + [f"cat_{c}" for c in CATEGORIES]
    + ["wall_time_s", "task_time_s", "no_call_tasks", "loop_or_limit_tasks",
       "loop_same_tasks", "loop_errors_tasks", "max_steps_tasks",
       "input_tokens", "output_tokens", "cached_input_tokens", "cost_usd"]
)


def check(condition, message):
    if not condition:
        raise SystemExit(f"CHECK FAILED: {message}")


def share(rows, key, value):
    """Return the part of the tasks of one type or category that have a pass grade."""
    chosen = [r for r in rows if r[key] == value]
    return sum(r["grade"] in PASS for r in chosen) / len(chosen), len(chosen)


def report_number(text, pattern):
    match = re.search(pattern, text)
    check(match, f"pattern {pattern} not found in the report")
    return float(match.group(1))


def build_row(name, group, folder, codename, report_file):
    run = RUNS / folder / "output" / codename
    rows = [json.loads(line) for line in (run / "results.jsonl").read_text().splitlines()]
    metrics = json.loads((run / "metrics.json").read_text())
    report = (BASELINE / report_file).read_text()

    ids = [r["task_id"] for r in rows]
    check(len(rows) == N_TASKS and len(set(ids)) == N_TASKS, f"{name}: not 200 different tasks")
    check(all(r["error"] is None for r in rows) or metrics["errors"] == sum(r["error"] is not None for r in rows),
          f"{name}: errors in results.jsonl differ from metrics.json")

    out = {"model": name, "codename": codename, "group": group, "tasks": len(rows)}
    out["score_all"] = round(sum(r["grade"] in PASS for r in rows) / len(rows), 4)
    for t in TYPES:
        value, count = share(rows, "difficulty", t)
        check(count == TYPE_COUNTS[t], f"{name}: {t} has {count} tasks")
        out[f"score_{t}"] = round(value, 4)
    for c in CATEGORIES:
        value, count = share(rows, "category", c)
        check(count == CATEGORY_COUNTS[c], f"{name}: {c} has {count} tasks")
        out[f"cat_{c}"] = round(value, 4)

    out["wall_time_s"] = round(metrics["run"]["wall_time_s"])
    out["task_time_s"] = round(sum(r["time_s"] for r in rows))
    out["no_call_tasks"] = sum(r["tool_calls"] == 0 for r in rows)
    for stop in ("loop_same", "loop_errors", "max_steps"):
        out[f"{stop}_tasks"] = sum(r["stop_reason"] == stop for r in rows)
    out["loop_or_limit_tasks"] = out["loop_same_tasks"] + out["loop_errors_tasks"] + out["max_steps_tasks"]
    out["input_tokens"] = sum(r["input_tokens"] for r in rows)
    out["output_tokens"] = sum(r["output_tokens"] for r in rows)
    external = "total_cost_usd" in metrics
    out["cached_input_tokens"] = sum(r["cached_input_tokens"] for r in rows) if external else ""
    out["cost_usd"] = round(sum(r["cost_usd"] for r in rows), 4) if external else ""

    # Check 1: metrics.json, written by the run, gives the same numbers.
    check(abs(metrics["score"] - out["score_all"]) < 1e-3, f"{name}: score differs from metrics.json")
    for t in TYPES:
        check(abs(metrics["by_difficulty"][t]["score"] - out[f"score_{t}"]) < 1e-3, f"{name}: {t} differs from metrics.json")
    for c in CATEGORIES:
        check(abs(metrics["by_category"][c]["score"] - out[f"cat_{c}"]) < 1e-3, f"{name}: {c} differs from metrics.json")
    health = metrics["health"]
    check(health["no_tool_call_tasks"] == out["no_call_tasks"], f"{name}: no call differs from metrics.json")
    for stop in ("loop_same", "loop_errors", "max_steps"):
        check(health[f"{stop}_tasks"] == out[f"{stop}_tasks"], f"{name}: {stop} differs from metrics.json")
    check(abs(metrics["total_time_s"] - out["task_time_s"]) <= 1, f"{name}: task time differs from metrics.json")
    check(abs(metrics["mean_input_tokens"] * N_TASKS - out["input_tokens"]) <= N_TASKS, f"{name}: input tokens differ from metrics.json")
    check(abs(metrics["mean_output_tokens"] * N_TASKS - out["output_tokens"]) <= N_TASKS, f"{name}: output tokens differ from metrics.json")
    if external:
        check(metrics["total_input_tokens"] == out["input_tokens"], f"{name}: input tokens differ from metrics.json")
        check(metrics["total_output_tokens"] == out["output_tokens"], f"{name}: output tokens differ from metrics.json")
        check(metrics["total_cached_input_tokens"] == out["cached_input_tokens"], f"{name}: cached tokens differ from metrics.json")
        check(abs(metrics["total_cost_usd"] - out["cost_usd"]) < 1e-3, f"{name}: cost differs from metrics.json")

    # Check 2: the report of the run, which a person reads, gives the same numbers.
    check(report_number(report, r"\| All \| 200 \| ([\d.]+) \|") == round(out["score_all"], 3), f"{name}: score differs from the report")
    for t in TYPES:
        check(report_number(report, rf"\| `{t}` \| \d+ \| ([\d.]+) \|") == round(out[f"score_{t}"], 3), f"{name}: {t} differs from the report")
    for c in CATEGORIES:
        check(report_number(report, rf"\| {c} \| \d+ \| ([\d.]+) \|") == round(out[f"cat_{c}"], 3), f"{name}: {c} differs from the report")
    check(report_number(report, r"no_tool_call_tasks (\d+)") == out["no_call_tasks"], f"{name}: no call differs from the report")
    check(report_number(report, r"Time of the job: (\d+) s") == out["wall_time_s"], f"{name}: time differs from the report")
    if external:
        check(report_number(report, r"Cost: ([\d.]+) USD") == round(out["cost_usd"], 2), f"{name}: cost differs from the report")
        check(report_number(report, r"Input tokens: (\d+)") == out["input_tokens"], f"{name}: input tokens differ from the report")
        check(report_number(report, r"Output tokens: (\d+)") == out["output_tokens"], f"{name}: output tokens differ from the report")
    return out


def main():
    table = [build_row(*model) for model in MODELS]
    with OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    print(f"Wrote {len(table)} rows to {OUTPUT}. All checks passed.")


if __name__ == "__main__":
    main()
