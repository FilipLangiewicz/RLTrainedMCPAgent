"""Write a small digest of the tool calls of each baseline run in `kernel_sources`.

`trajectories.jsonl` stays on Kaggle. The digest gives the error analysis the calls without this file.
"""
import json
from pathlib import Path

RESULT_LIMIT = 1500
OUTPUT = Path("/kaggle/working/calls-digest")
OUTPUT.mkdir(parents=True)

# A merged run also has the two files of its shards. Only the merged file has all tasks.
files = {}
for path in Path("/kaggle/input").rglob("trajectories.jsonl"):
    lines = path.read_text(encoding="utf-8").splitlines()
    print(path, len(lines), flush=True)
    codename = next(p.name for p in path.parents if p.name.startswith("baseline-"))
    if len(lines) > len(files.get(codename, [])):
        files[codename] = lines

for codename, lines in files.items():
    with open(OUTPUT / f"calls-{codename}.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            t = json.loads(line)
            calls = [{**c, "result": c["result"][:RESULT_LIMIT]} for c in t["tool_calls"]]
            row = {"task_id": t["task_id"], "stop_reason": t["stop_reason"], "final_answer": t["final_answer"], "calls": calls}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(codename, len(lines), "tasks", flush=True)
