"""Make the figures of the baseline comparison from results_baseline.csv.

Usage: python -m src.plot_baselines
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASELINE = Path("data/results/baseline")
CSV = BASELINE / "results_baseline.csv"
FIGURES = BASELINE / "figures"

# The order of the models in the figures: one family together, the smaller model first.
ORDER = [
    "Haiku 5.5", "Sonnet 5.5", "Opus 5.5", "Gemini 4 Argon",
    "Bielik 1.5B", "Bielik 4.5B", "Qwen3.5-2B", "Qwen3.5-4B", "Gemma 4 E2B", "Gemma 4 E4B",
]
TYPES = ["easy", "multi_step", "refusal"]
CATEGORIES = ["bulk", "create", "log", "query", "refusal", "sprint", "update", "workflow"]
COLORS = {"local": "#d95f02", "external": "#1b6ca8"}


def read_results():
    """Return the rows of results_baseline.csv, in the order of the figures."""
    with CSV.open() as f:
        rows = {r["model"]: r for r in csv.DictReader(f)}
    data = {}
    for name in ORDER:
        r = rows[name]
        data[name] = {
            "group": r["group"],
            "types": {"All": float(r["score_all"]), **{t: float(r[f"score_{t}"]) for t in TYPES}},
            "categories": {c: float(r[f"cat_{c}"]) for c in CATEGORIES},
            "no_call": int(r["no_call_tasks"]),
            "loop_or_limit": int(r["loop_or_limit_tasks"]),
            "cost": float(r["cost_usd"]) if r["cost_usd"] else None,
        }
    return data


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_groups(data):
    """Mean score of the local group and of the external group, with the range."""
    labels = ["All"] + TYPES
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.35
    for i, group in enumerate(["local", "external"]):
        rows = [data[n] for n in ORDER if data[n]["group"] == group]
        values = np.array([[r["types"][k] for k in labels] for r in rows])
        mean = values.mean(axis=0)
        err = [mean - values.min(axis=0), values.max(axis=0) - mean]
        x = np.arange(len(labels)) + (i - 0.5) * width
        ax.bar(x, mean, width, yerr=err, capsize=4, color=COLORS[group],
               label=f"{group} ({len(rows)} models)")
        for xi, m, top in zip(x, mean, values.max(axis=0)):
            ax.text(xi, top + 0.02, f"{m:.2f}", ha="center", fontweight="bold")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels([l.replace("_", " ") for l in labels])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score (mean of the group, bar = min to max)")
    ax.set_title("Local models and external models: score by task type")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    save(fig, "1-groups-by-type.png")


def plot_types(data):
    fig, ax = plt.subplots(figsize=(11, 4.8))
    width = 0.27
    names = ORDER
    x = np.arange(len(names))
    for i, (t, shade) in enumerate(zip(TYPES, [1.0, 0.7, 0.4])):
        ax.bar(x + (i - 1) * width, [data[n]["types"][t] for n in names], width,
               color=[matplotlib.colors.to_rgba(COLORS[data[n]["group"]], shade) for n in names],
               label=t.replace("_", " "))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Score by task type (dark = easy, medium = multi step, light = refusal)")
    ax.axvline(3.5, color="grey", linestyle="--", linewidth=1)
    save(fig, "2-types-by-model.png")


def plot_heatmap(data):
    names = ORDER
    grid = np.array([[data[n]["categories"][c] for c in CATEGORIES] for n in names])
    fig, ax = plt.subplots(figsize=(9, 5.5))
    image = ax.imshow(grid, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    for i in range(len(names)):
        for j in range(len(CATEGORIES)):
            ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center",
                    color="white" if grid[i, j] < 0.6 else "black", fontsize=9)
    ax.set_xticks(range(len(CATEGORIES)))
    ax.set_xticklabels(CATEGORIES)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.axhline(3.5, color="white", linewidth=3)
    ax.set_title("Score by category")
    fig.colorbar(image, ax=ax, label="Score")
    save(fig, "3-categories-heatmap.png")


def plot_cost(data):
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for name in ORDER:
        group = data[name]["group"]
        cost = data[name]["cost"]
        if cost is None:
            continue
        score = data[name]["types"]["All"]
        ax.scatter(cost, score, s=90, color=COLORS[group])
        offset = {"Opus 5.5": (-30, 12), "Gemini 4 Argon": (-20, -20)}.get(name, (8, -12))
        ax.annotate(name, (cost, score), textcoords="offset points", xytext=offset)
    ax.set_xlabel("Cost of the 200 tasks (USD, API price)")
    ax.set_ylabel("Score")
    ax.set_ylim(0.6, 1.02)
    ax.set_xlim(0, 7.5)
    ax.set_title("External models: score and cost")
    save(fig, "4-score-vs-cost.png")


def plot_problems(data):
    local = [n for n in ORDER if data[n]["group"] == "local"]
    problems = {
        "No tool call": lambda d: d["no_call"],
        "Loop or limit": lambda d: d["loop_or_limit"],
    }
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(local))
    width = 0.38
    for i, (label, get) in enumerate(problems.items()):
        ax.bar(x + (i - 0.5) * width, [get(data[n]) for n in local], width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(local, rotation=20, ha="right")
    ax.set_ylabel("Tasks (of 200)")
    ax.set_title("Local models: the two main kinds of failure")
    ax.legend()
    save(fig, "5-local-failures.png")


def wilson(score, n=200, z=1.96):
    """Return the 95 percent interval of a share, as the distance down and up."""
    centre = (score + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(score * (1 - score) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return score - (centre - half), (centre + half) - score


def plot_ranking(data):
    """Rank all models by the score on all tasks. The line is the 95 percent interval."""
    ranked = sorted(ORDER, key=lambda n: data[n]["types"]["All"])
    scores = [data[n]["types"]["All"] for n in ranked]
    err = np.array([wilson(s) for s in scores]).T
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(ranked, scores, xerr=err, capsize=3,
            color=[COLORS[data[n]["group"]] for n in ranked])
    for i, s in enumerate(scores):
        ax.text(min(s + err[1][i] + 0.015, 1.0), i, f"{s:.3f}", va="center", fontweight="bold")
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("Score on all 200 tasks (line = 95% interval of the score)")
    ax.set_title("Ranking of the models")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[g]) for g in ("external", "local")]
    ax.legend(handles, ["external", "local"], loc="lower right")
    save(fig, "6-ranking.png")


def main():
    data = read_results()
    plot_groups(data)
    plot_types(data)
    plot_heatmap(data)
    plot_cost(data)
    plot_problems(data)
    plot_ranking(data)


if __name__ == "__main__":
    main()
