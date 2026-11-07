"""Write the answers of each run in `kernel_sources` into a small file.

`trajectories.jsonl` stays on Kaggle. The report of a reference model needs only the instruction and the answer of each task.
"""
import json
from pathlib import Path

OUTPUT = Path("/kaggle/working/answers")
OUTPUT.mkdir(parents=True)

for path in sorted(Path("/kaggle/input").rglob("*")):
    if path.is_file():
        print(path, path.stat().st_size, flush=True)

for path in Path("/kaggle/input").rglob("trajectories.jsonl"):
    codename = path.parent.name
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with open(OUTPUT / f"answers-{codename}.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for t in rows:
            row = {"task_id": t["task_id"], "instruction": t["instruction"], "final_answer": t["final_answer"],
                   "thinking": bool(t.get("thinking"))}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(codename, len(rows), "tasks", flush=True)
