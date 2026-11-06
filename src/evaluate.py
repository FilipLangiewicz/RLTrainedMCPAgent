"""Evaluation: run the agent on a task set, grade each task, and write the results and the metrics."""

import argparse
import json
import platform
import re
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from src.agent import DEFAULT_ERROR_LIMIT, DEFAULT_LOOP_LIMIT, DEFAULT_MAX_STEPS, DEFAULT_PROMPT, Trajectory, run_task
from src.environment import load_board
from src.models import ModelStopped, Prompt, check_config, load_prompt, make_model
from src.tasks import DATA_DIR, board_path, load_tasks
from src.tools import build_server
from src.verifier import grade

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "jobs" / "runs"
GOOD = ("correct", "correct_refusal")
COMMENT_PLACEHOLDER = "Write this section by hand: at most 6 short lines."


def is_garbled(text: str) -> bool:
    """True if a model output looks like the output of a broken model (NaN logits give a row of '!')."""
    chars = [c for c in text if not c.isspace()]
    if "\ufffd" in text:
        return True
    # A short rest of a special token, for example '<|"|>', is not a broken output.
    return len(chars) >= 8 and sum(c.isalpha() for c in chars) < 0.3 * len(chars)


def load_config(codename: str, runs_dir: Path = RUNS_DIR) -> dict:
    """Find `<codename>.yaml` in a job folder. A path to a YAML file also works (for a smoke test)."""
    path = Path(codename)
    if path.suffix in (".yaml", ".yml") and path.is_file():
        matches, codename = [path], path.stem
    else:
        matches = sorted(Path(runs_dir).glob(f"*/{codename}.yaml"))
    if len(matches) != 1:
        raise FileNotFoundError(f"need exactly one config for {codename}, found {[str(m) for m in matches]}")
    cfg = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    cfg["codename"] = codename
    return cfg


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _versions() -> dict:
    versions = {"python": platform.python_version(), "torch": None, "transformers": None, "device": platform.processor() or "cpu"}
    try:
        import torch

        versions["torch"] = torch.__version__
        if torch.cuda.is_available():
            versions["device"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    try:
        import transformers

        versions["transformers"] = transformers.__version__
    except ImportError:
        pass
    return versions


def evaluate_task(task, model, prompt: Prompt, max_steps: int, loop_limit: int | None = DEFAULT_LOOP_LIMIT,
                  error_limit: int | None = DEFAULT_ERROR_LIMIT, data_dir: Path = DATA_DIR) -> tuple[dict, dict]:
    """Do one task on a new copy of its board. Return the result line and the trajectory."""
    initial = load_board(board_path(task.board, data_dir))
    board = initial.copy_board()
    try:
        traj = run_task(model, build_server(board), task.instruction, prompt, max_steps, task.id, loop_limit, error_limit)
    except ModelStopped:
        raise
    except Exception as e:  # noqa: BLE001  A failure of one task must not stop the run.
        traj = Trajectory(task_id=task.id, instruction=task.instruction, stop_reason="error", error=f"{type(e).__name__}: {e}")
    if traj.stop_reason == "error":
        model.free_memory()
        result_grade, reason = "incorrect", f"error: {traj.error}"
    else:
        g = grade(task, initial, board, traj.final_answer)
        result_grade, reason = g.grade, g.reason
    outputs = [m["content"] for m in traj.messages if m["role"] == "assistant" and isinstance(m.get("content"), str)]
    result = {
        "task_id": task.id, "author": task.author, "board": task.board,
        "difficulty": task.difficulty, "category": task.category,
        "grade": result_grade, "reason": reason, "stop_reason": traj.stop_reason,
        "steps": traj.steps, "tool_calls": len(traj.tool_calls),
        "invalid_calls": traj.invalid_calls, "tool_errors": traj.tool_errors,
        "empty_answer": traj.stop_reason == "answer" and not traj.final_answer.strip(),
        "garbled": any(is_garbled(text) for text in outputs),
        "input_tokens": traj.input_tokens, "output_tokens": traj.output_tokens, "time_s": traj.time_s,
        "error": traj.error,
    }
    return result, traj.model_dump()


def compute_metrics(results: list[dict]) -> dict:
    def summary(rows):
        n = len(rows)
        return {
            "n": n,
            "score": round(sum(r["grade"] in GOOD for r in rows) / n, 4) if n else 0.0,
            "correct": round(sum(r["grade"] == "correct" for r in rows) / n, 4) if n else 0.0,
            "correct_refusal": round(sum(r["grade"] == "correct_refusal" for r in rows) / n, 4) if n else 0.0,
        }

    def mean(field):
        return round(sum(r[field] for r in results) / len(results), 3) if results else 0.0

    groups = {"difficulty": defaultdict(list), "category": defaultdict(list)}
    for r in results:
        for field, group in groups.items():
            group[r[field]].append(r)
    return {
        **summary(results),
        "by_difficulty": {k: summary(v) for k, v in sorted(groups["difficulty"].items())},
        "by_category": {k: summary(v) for k, v in sorted(groups["category"].items())},
        "mean_steps": mean("steps"),
        "mean_invalid_calls": mean("invalid_calls"),
        "mean_tool_errors": mean("tool_errors"),
        "mean_input_tokens": mean("input_tokens"),
        "mean_output_tokens": mean("output_tokens"),
        "mean_time_s": mean("time_s"),
        "total_time_s": round(sum(r["time_s"] for r in results), 3),
        "errors": sum(r["error"] is not None for r in results),
        "health": {
            "empty_answers": sum(r["empty_answer"] for r in results),
            "garbled_tasks": sum(r["garbled"] for r in results),
            "no_tool_call_tasks": sum(r["tool_calls"] == 0 for r in results),
            "invalid_call_tasks": sum(r["invalid_calls"] > 0 for r in results),
            "max_steps_tasks": sum(r["stop_reason"] == "max_steps" for r in results),
            "loop_same_tasks": sum(r["stop_reason"] == "loop_same" for r in results),
            "loop_errors_tasks": sum(r["stop_reason"] == "loop_errors" for r in results),
        },
    }


def _cell(text: str, limit: int = 300) -> str:
    text = " ".join((text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def write_report(output_dir: Path) -> None:
    """Write report-<codename>.md in the form of AGENTS.md. A person writes the comment and the Why cells later."""
    output_dir = Path(output_dir)
    results = _read_jsonl(output_dir / "results.jsonl")
    trajectories = {t["task_id"]: t for t in _read_jsonl(output_dir / "trajectories.jsonl")}
    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    run = metrics["run"]
    lines = [
        f"# Report of {run['codename']}", "",
        f"Model: `{Path(run['model']['path']).name}`. Time of the job: {run['wall_time_s']:.0f} s.", "",
        "| Task type | Tasks | Score |", "|---|---|---|",
        f"| All | {metrics['n']} | {metrics['score']:.3f} |",
        # A short run can have no task of a type.
        *[f"| `{k}` | {v['n']} | {v['score']:.3f} |" for k, v in sorted(metrics["by_difficulty"].items(), key=_type_order)], "",
        "| Category | Tasks | Score |", "|---|---|---|",
        *[f"| {k} | {v['n']} | {v['score']:.3f} |" for k, v in sorted(metrics["by_category"].items())], "",
        "Health: " + ", ".join(f"{k} {v}" for k, v in metrics["health"].items()) + ".", "",
        "## What SFT and RL must teach", "",
        COMMENT_PLACEHOLDER, "",
        "## Tasks", "",
        "Points: 1 for `correct` and `correct_refusal`, 0 for `incorrect`.", "",
        "| Task | Category | Instruction | Calls | Answer of the model | Reason | Why | Points |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        t = trajectories.get(r["task_id"], {})
        answer = t.get("final_answer") or (f"(no answer: {r['stop_reason']})")
        points = int(r["grade"] in GOOD)
        lines.append(f"| {r['task_id']} | {r['category']} | {_cell(t.get('instruction', ''))} | {r['tool_calls']} "
                     f"| {_cell(answer)} | {_cell(r['reason'])} |  | {points} |")
    (output_dir / f"report-{run['codename']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _type_order(item: tuple[str, dict]) -> int:
    order = ("easy", "multi_step", "refusal")
    return order.index(item[0]) if item[0] in order else len(order)


def fill_report(report: Path, why: Path, comment: Path, output: Path) -> None:
    """Put the hand-written comment and Why cells into a report of write_report. Write nothing if a check fails.

    The file `why` has one line for each task: `test-NNN text`. The file `comment` has the lines of the comment.
    """
    text = Path(report).read_text(encoding="utf-8")
    cells = dict(line.split(" ", 1) if " " in line else (line, "")
                 for line in Path(why).read_text(encoding="utf-8").splitlines() if line.strip())
    cells = {task: cell.strip() for task, cell in cells.items()}
    items = [line for line in Path(comment).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = re.findall(r"^\| (test-\d+) \|.*\|  \| [01] \|$", text, flags=re.M)
    problems = []
    if COMMENT_PLACEHOLDER not in text or not rows or text.count("\n| test-") != len(rows):
        problems.append("the report is not an unfilled report of write_report")
    if set(cells) != set(rows):
        problems.append(f"the tasks of the Why file differ from the report: {sorted(set(cells) ^ set(rows))[:9]}")
    for task, cell in cells.items():
        if not cell or "|" in cell:
            problems.append(f"{task}: the Why cell is empty or has |")
        problems += [f"{task}: a sentence has more than 25 words: {s[:50]}"
                     for s in re.split(r"(?<=[.!?:]) ", cell) if len(s.split()) > 25]
    # Different tasks have different calls, so many equal cells show a template.
    if len(set(cells.values())) < len(cells) / 2:
        problems.append("too many equal Why cells")
    if not items or len(items) > 6 or not all(line.startswith("- ") for line in items):
        problems.append('the comment must have 1 to 6 lines, and each line starts with "- "')
    problems += [f"a comment line has more than 40 words: {line[:50]}" for line in items if len(line.split()) > 40]
    if len(re.findall(r"test-\d{3}", "\n".join(items))) > 3:
        problems.append("the comment has more than 3 task ids")
    if problems:
        raise ValueError("\n".join(problems))
    text = text.replace(COMMENT_PLACEHOLDER, "\n".join(items), 1)
    text = re.sub(r"^(\| (test-\d+) \|.*\|)  (\| [01] \|)$", lambda m: f"{m[1]} {cells[m[2]]} {m[3]}", text, flags=re.M)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(text, encoding="utf-8", newline="\n")


def _write_metrics(output_dir: Path, results: list[dict], run: dict) -> dict:
    metrics = {**compute_metrics(results), "run": run}
    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if (output_dir / "trajectories.jsonl").exists():
        write_report(output_dir)
    return metrics


def run_evaluation(cfg: dict, output_dir: Path, shard: tuple[int, int] = (0, 1), model=None,
                   data_dir: Path = DATA_DIR, resume: bool = False) -> dict:
    """Run the agent on the tasks of shard `i` of `n`. Write results.jsonl, trajectories.jsonl and metrics.json.

    The checks of the model config and of the prompt file stop the run before the first task.
    With `resume`, the run keeps the results in the folder and does only the other tasks.
    """
    i, n = shard
    agent_cfg = cfg.get("agent") or {}
    cfg["model"] = check_config(cfg["model"])
    prompt = load_prompt("system", agent_cfg.get("prompt", DEFAULT_PROMPT))
    max_steps = agent_cfg.get("max_steps", DEFAULT_MAX_STEPS)
    loop_limit = agent_cfg.get("loop_limit", DEFAULT_LOOP_LIMIT)
    error_limit = agent_cfg.get("error_limit", DEFAULT_ERROR_LIMIT)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(cfg["tasks"]["split"], data_dir)
    if cfg["tasks"].get("limit"):
        tasks = tasks[: cfg["tasks"]["limit"]]
    if cfg["tasks"].get("ids"):
        tasks = [t for t in tasks if t.id in cfg["tasks"]["ids"]]
    tasks = [t for pos, t in enumerate(tasks) if pos % n == i]
    model = model or make_model(cfg["model"])

    started = datetime.now(UTC)
    results = _read_jsonl(output_dir / "results.jsonl") if resume and (output_dir / "results.jsonl").exists() else []
    complete = {r["task_id"] for r in results}
    mode = "a" if resume else "w"
    with open(output_dir / "results.jsonl", mode, encoding="utf-8", newline="\n") as fr, \
            open(output_dir / "trajectories.jsonl", mode, encoding="utf-8", newline="\n") as ft:
        for task in (t for t in tasks if t.id not in complete):
            result, traj = evaluate_task(task, model, prompt, max_steps, loop_limit, error_limit, data_dir)
            results.append(result)
            # Write each line at once, so that a stopped run keeps its results.
            fr.write(json.dumps(result, ensure_ascii=False) + "\n")
            ft.write(json.dumps(traj, ensure_ascii=False) + "\n")
            fr.flush()
            ft.flush()
            print(f"{task.id} {result['grade']} steps={result['steps']} time={result['time_s']}s", flush=True)

    run = {
        "codename": cfg["codename"],
        "config": {k: v for k, v in cfg.items() if k != "codename"},
        "model": model.describe(),
        "prompt_version": prompt.version,
        "prompt_sha256": prompt.sha256,
        "git_commit": _git_commit(),
        **_versions(),
        "date": started.isoformat(timespec="seconds"),
        "wall_time_s": round((datetime.now(UTC) - started).total_seconds(), 3),
        "shards": [f"{i}/{n}"],
    }
    return _write_metrics(output_dir, results, run)


def merge(output_dirs: list[Path], output_dir: Path) -> dict:
    """Merge the results of all shards into one folder with one metrics.json."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results, trajectories, runs = [], [], []
    for d in map(Path, output_dirs):
        results += _read_jsonl(d / "results.jsonl")
        trajectories += _read_jsonl(d / "trajectories.jsonl")
        runs.append(json.loads((d / "metrics.json").read_text(encoding="utf-8"))["run"])
    ids = [r["task_id"] for r in results]
    if len(ids) != len(set(ids)):
        raise ValueError("a task occurs in more than one shard")
    if len({r["codename"] for r in runs}) != 1:
        raise ValueError(f"the shards have different codenames: {sorted({r['codename'] for r in runs})}")
    results.sort(key=lambda r: r["task_id"])
    trajectories.sort(key=lambda t: t["task_id"])
    _write_jsonl(output_dir / "results.jsonl", results)
    _write_jsonl(output_dir / "trajectories.jsonl", trajectories)
    run = {**runs[0], "shards": sorted(s for r in runs for s in r["shards"]),
           "wall_time_s": max(r["wall_time_s"] for r in runs), "devices": [r["device"] for r in runs]}
    return _write_metrics(output_dir, results, run)


def _shard(text: str) -> tuple[int, int]:
    i, n = map(int, text.split("/"))
    if not 0 <= i < n:
        raise argparse.ArgumentTypeError("use i/n with 0 <= i < n")
    return i, n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the evaluation, or merge the results of shards.")
    parser.add_argument("codename", nargs="?", help="codename of a config in jobs/runs/, or a path to a YAML file")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fill", type=Path, metavar="REPORT", help="put the hand-written parts into this report")
    parser.add_argument("--why", type=Path, help="with --fill: the file with the Why cells")
    parser.add_argument("--comment", type=Path, help="with --fill: the file with the comment")
    parser.add_argument("--shard", type=_shard, default=(0, 1), help="i/n, for example 0/2")
    parser.add_argument("--limit", type=int, help="use only the first N tasks")
    parser.add_argument("--resume", action="store_true", help="keep the results in --output and do the other tasks")
    parser.add_argument("--merge", type=Path, nargs="+", metavar="FOLDER", help="merge these shard folders")
    args = parser.parse_args(argv)
    if args.fill:
        if not (args.why and args.comment):
            parser.error("--fill needs --why and --comment")
        try:
            fill_report(args.fill, args.why, args.comment, args.output)
        except ValueError as e:
            sys.exit(str(e))
        return
    if args.merge:
        metrics = merge(args.merge, args.output)
    elif args.codename:
        cfg = load_config(args.codename)
        if args.limit:
            cfg["tasks"]["limit"] = args.limit
        try:
            metrics = run_evaluation(cfg, args.output, args.shard, resume=args.resume)
        except ModelStopped as e:
            sys.exit(f"The run stopped: {e}\nThe complete tasks are in {args.output}. To continue, use --resume.")
    else:
        parser.error("give a codename or --merge")
    summary = {k: metrics[k] for k in ("n", "score", "correct", "correct_refusal")}
    print(json.dumps({**summary, "by_difficulty": metrics["by_difficulty"]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
