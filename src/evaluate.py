"""Evaluation: run the agent on a task set, grade each task, and write the results and the metrics."""

import argparse
import json
import platform
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from src.agent import DEFAULT_MAX_STEPS, DEFAULT_PROMPT, Trajectory, run_task
from src.environment import load_board
from src.models import Prompt, check_config, load_prompt, make_model
from src.tasks import DATA_DIR, board_path, load_tasks
from src.tools import build_server
from src.verifier import grade

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "jobs" / "runs"
GOOD = ("correct", "correct_refusal")


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


def evaluate_task(task, model, prompt: Prompt, max_steps: int, data_dir: Path = DATA_DIR) -> tuple[dict, dict]:
    """Do one task on a new copy of its board. Return the result line and the trajectory."""
    initial = load_board(board_path(task.board, data_dir))
    board = initial.copy_board()
    try:
        traj = run_task(model, build_server(board), task.instruction, prompt, max_steps, task.id)
    except Exception as e:  # noqa: BLE001  A failure of one task must not stop the run.
        traj = Trajectory(task_id=task.id, instruction=task.instruction, stop_reason="error", error=f"{type(e).__name__}: {e}")
    if traj.stop_reason == "error":
        result_grade, reason = "incorrect", f"error: {traj.error}"
    else:
        g = grade(task, initial, board, traj.final_answer)
        result_grade, reason = g.grade, g.reason
    result = {
        "task_id": task.id, "author": task.author, "board": task.board,
        "difficulty": task.difficulty, "category": task.category,
        "grade": result_grade, "reason": reason, "stop_reason": traj.stop_reason,
        "steps": traj.steps, "invalid_calls": traj.invalid_calls, "tool_errors": traj.tool_errors,
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
    }


def _write_metrics(output_dir: Path, results: list[dict], run: dict) -> dict:
    metrics = {**compute_metrics(results), "run": run}
    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


def run_evaluation(cfg: dict, output_dir: Path, shard: tuple[int, int] = (0, 1), model=None,
                   data_dir: Path = DATA_DIR) -> dict:
    """Run the agent on the tasks of shard `i` of `n`. Write results.jsonl, trajectories.jsonl and metrics.json.

    The checks of the model config and of the prompt file stop the run before the first task.
    """
    i, n = shard
    agent_cfg = cfg.get("agent") or {}
    cfg["model"] = check_config(cfg["model"])
    prompt = load_prompt("system", agent_cfg.get("prompt", DEFAULT_PROMPT))
    max_steps = agent_cfg.get("max_steps", DEFAULT_MAX_STEPS)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(cfg["tasks"]["split"], data_dir)
    if cfg["tasks"].get("limit"):
        tasks = tasks[: cfg["tasks"]["limit"]]
    tasks = [t for pos, t in enumerate(tasks) if pos % n == i]
    model = model or make_model(cfg["model"])

    started = datetime.now(UTC)
    results = []
    with open(output_dir / "results.jsonl", "w", encoding="utf-8", newline="\n") as fr, \
            open(output_dir / "trajectories.jsonl", "w", encoding="utf-8", newline="\n") as ft:
        for task in tasks:
            result, traj = evaluate_task(task, model, prompt, max_steps, data_dir)
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
    parser.add_argument("--shard", type=_shard, default=(0, 1), help="i/n, for example 0/2")
    parser.add_argument("--limit", type=int, help="use only the first N tasks")
    parser.add_argument("--merge", type=Path, nargs="+", metavar="FOLDER", help="merge these shard folders")
    args = parser.parse_args(argv)
    if args.merge:
        metrics = merge(args.merge, args.output)
    elif args.codename:
        cfg = load_config(args.codename)
        if args.limit:
            cfg["tasks"]["limit"] = args.limit
        metrics = run_evaluation(cfg, args.output, args.shard)
    else:
        parser.error("give a codename or --merge")
    summary = {k: metrics[k] for k in ("n", "score", "correct", "correct_refusal")}
    print(json.dumps({**summary, "by_difficulty": metrics["by_difficulty"]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
