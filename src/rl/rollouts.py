"""Groups of rollouts with the agent loop of the evaluation, the reward and the group statistics."""

import random
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from src.agent import run_task
from src.environment import diff, load_board
from src.tasks import CATEGORIES, CHANGE_CATEGORIES, board_path
from src.tools import build_server
from src.verifier import grade, match_changes

GOOD = ("correct", "correct_refusal")
REFUSAL_WRITE = -0.2
PARTIAL_WEIGHT = 0.2


@dataclass
class Rollout:
    task: object
    group: int
    reward: float | None = 0.0
    partial: float = 0.0
    stop_reason: str = ""
    grade: str = ""
    steps: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    time_s: float = 0.0
    turns: list = field(default_factory=list)
    context_limit: bool = False
    engine_error: str | None = None

    @property
    def valid(self) -> bool:
        """A rollout at the context limit or with a failure of the engine does not go to the loss."""
        return not self.context_limit and self.engine_error is None

    def row(self, with_task_id: bool = True) -> dict:
        row = {"group": self.group, "category": self.task.category, "difficulty": self.task.difficulty,
               "reward": self.reward, "partial_reward": self.partial, "grade": self.grade,
               "stop_reason": self.stop_reason, "context_limit": self.context_limit, "engine_error": self.engine_error,
               "steps": self.steps, "tool_calls": self.tool_calls, "input_tokens": self.input_tokens,
               "output_tokens": self.output_tokens, "time_s": self.time_s}
        return {"task_id": self.task.id, **row} if with_task_id else row


def f_beta(matched: int, expected: int, actual: int, beta: float = 0.5) -> float:
    if matched == 0:
        return 0.0
    precision, recall = matched / actual, matched / expected
    return (1 + beta**2) * precision * recall / (beta**2 * precision + recall)


def reward(task, initial, final, final_answer: str, stop_reason: str, kind: str = "binary") -> tuple[float, float, str]:
    """Return the reward, the partial part and the grade.

    A rollout that stops with an error gets 0. A rollout that the loop rules or the step limit stop also gets 0.
    The exception is a write on the board in a refusal task: it always gives -0.2.
    """
    if stop_reason == "error":
        return 0.0, 0.0, "error"
    g = grade(task, initial, final, final_answer).grade
    actual = diff(initial, final)
    if task.category == "refusal" and actual:
        return REFUSAL_WRITE, 0.0, g
    if stop_reason != "answer":
        return 0.0, 0.0, g
    if g in GOOD:
        return 1.0, 0.0, g
    if kind == "partial" and task.category in CHANGE_CATEGORIES:
        missing, _ = match_changes(task.changes, actual)
        matched = len(task.changes) - len(missing)
        part = round(PARTIAL_WEIGHT * f_beta(matched, len(task.changes), len(actual)), 4)
        return part, part, g
    return 0.0, 0.0, g


def run_one(model, task, group: int, prompt, agent: dict, reward_kind: str) -> Rollout:
    initial = load_board(board_path(task.board))
    board = initial.copy_board()
    result = Rollout(task=task, group=group)
    traj = run_task(model, build_server(board), task.instruction, prompt, agent["max_steps"], task.id,
                    agent["loop_limit"], agent["error_limit"])
    result.reward, result.partial, result.grade = reward(task, initial, board, traj.final_answer, traj.stop_reason,
                                                         reward_kind)
    result.stop_reason, result.steps, result.tool_calls = traj.stop_reason, traj.steps, len(traj.tool_calls)
    result.input_tokens, result.output_tokens, result.time_s = traj.input_tokens, traj.output_tokens, traj.time_s
    result.turns = getattr(model, "turns", [])
    result.context_limit = getattr(model, "context_limit", False)
    result.engine_error = getattr(model, "engine_error", None)
    if not result.valid:
        result.reward = None
    return result


def run_rollouts(engine, jobs: list[tuple[object, int]], prompt, agent: dict, reward_kind: str,
                 temperature: float | None = None) -> list[Rollout]:
    """Run each (task, group) job once. The engine gives the lanes: a lane runs its jobs one after the other."""
    lanes = max(1, min(engine.lanes, len(jobs)))

    def lane(index: int) -> list[tuple[int, Rollout]]:
        done = []
        for pos in range(index, len(jobs), lanes):
            task, group = jobs[pos]
            model = engine.model_for_rollout(index, temperature)
            try:
                done.append((pos, run_one(model, task, group, prompt, agent, reward_kind)))
            except Exception as e:  # noqa: BLE001  One failed rollout must not stop the step.
                print(traceback.format_exc(limit=3), file=sys.stderr, flush=True)
                done.append((pos, Rollout(task=task, group=group, reward=None, stop_reason="error",
                                          engine_error=f"{type(e).__name__}: {e}")))
        return done

    with ThreadPoolExecutor(max_workers=lanes) as pool:
        results = [r for part in pool.map(lane, range(lanes)) for r in part]
    return [r for _, r in sorted(results, key=lambda x: x[0])]


def select_tasks(tasks: list, count: int, seed: int) -> list:
    """Take the tasks round robin over the categories, so that a short run still covers all categories."""
    rng = random.Random(seed)
    groups = {c: [t for t in tasks if t.category == c] for c in CATEGORIES}
    for group in groups.values():
        rng.shuffle(group)
    longest = max((len(g) for g in groups.values()), default=0)
    order = [groups[c][i] for i in range(longest) for c in CATEGORIES if i < len(groups[c])]
    return order[:count]


def group_stats(rollouts: list[Rollout]) -> dict:
    """The statistics of the groups: mean reward, the share of groups with mixed rewards, times and token counts."""
    groups: dict[int, list[Rollout]] = {}
    for r in rollouts:
        groups.setdefault(r.group, []).append(r)
    n = len(groups) or 1
    valid = [r for r in rollouts if r.valid]

    def mixed(g, key):
        values = {getattr(r, key) for r in g if r.valid}
        return len(values) > 1

    def mean(values):
        values = list(values)
        return round(sum(values) / len(values), 4) if values else 0.0

    by_category = {}
    for c in CATEGORIES:
        rows = [r.reward for r in valid if r.task.category == c]
        if rows:
            by_category[c] = mean(rows)
    times = sorted(r.time_s for r in rollouts)
    return {
        "rollouts": len(rollouts), "valid_rollouts": len(valid), "groups": len(groups),
        "context_limit": sum(r.context_limit for r in rollouts),
        "engine_errors": sum(r.engine_error is not None for r in rollouts),
        "mean_reward": mean(r.reward for r in valid),
        "mean_partial_reward": mean(r.partial for r in valid),
        "success": mean(r.grade in GOOD and r.reward == 1.0 for r in valid),
        "mixed_share": round(sum(mixed(g, "reward") for g in groups.values()) / n, 4),
        "all_zero_share": round(sum(all((r.reward or 0) <= 0 for r in g if r.valid) for g in groups.values()) / n, 4),
        "all_one_share": round(sum(all(r.reward == 1 for r in g if r.valid) for g in groups.values()) / n, 4),
        "reward_by_category": by_category,
        "rollout_time_s": {"mean": mean(times), "median": times[len(times) // 2] if times else None,
                           "max": times[-1] if times else None},
        "input_tokens_mean": mean(r.input_tokens for r in rollouts),
        "output_tokens_mean": mean(r.output_tokens for r in rollouts),
        "stop_reasons": {s: sum(r.stop_reason == s for r in rollouts) for s in sorted({r.stop_reason for r in rollouts})},
    }
