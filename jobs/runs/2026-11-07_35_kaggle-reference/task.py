"""Run the evaluation of a reference model in a Kaggle benchmark task. Only this kind of job has the model proxy."""
import os
import subprocess
import sys
from pathlib import Path

import kaggle_benchmarks as kbench

REPO = "https://github.com/FilipLangiewicz/RLTrainedMCPAgent.git"
BRANCH = "06-e1-baselines"
CLONE = "/tmp/repo"
LIMIT = None
EFFORT = "medium"
# The push of a task also runs the default model. This list keeps that run free.
MODELS = {
    "anthropic/claude-haiku-5-5": "claude-haiku-5-5",
    "anthropic/claude-sonnet-5-5@default": "claude-sonnet-5-5",
    "anthropic/claude-opus-5-5@default": "claude-opus-5-5",
    "google/gemini-4-argon": "gemini-4-argon",
}


@kbench.task(name="kaggle_reference")
def kaggle_reference(llm) -> bool:
    if llm.model not in MODELS:
        print("SKIP", llm.model, flush=True)
        return True
    codename = "baseline-kaggle-" + MODELS[llm.model]
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", BRANCH, REPO, CLONE], check=True)
    head = subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("HEAD", head, sys.version, flush=True)
    packages = ["mcp", "pydantic", "openai", "pyyaml", "python-dotenv"]
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *packages], check=False)

    import yaml

    base = os.environ["MODEL_PROXY_URL"].removesuffix("/openapi").removesuffix("/genai") + "/openapi"
    config = Path(f"/tmp/{codename}.yaml")
    config.write_text(yaml.safe_dump({
        "model": {"backend": "openai", "path": llm.model, "base_url": base, "api_key_env": "MODEL_PROXY_API_KEY",
                  "temperature": None, "reasoning_effort": EFFORT},
        "agent": {"prompt": "v3", "max_steps": 25, "loop_limit": 3, "error_limit": 5},
        "tasks": {"split": "test", "limit": LIMIT},
    }))
    # The task ends normally after a failure, so that the results stay.
    output = f"/kaggle/working/{codename}"
    done = subprocess.run([sys.executable, "-m", "src.evaluate", str(config), "--output", output],
                          cwd=CLONE, capture_output=True, text=True)
    print(done.stdout[-3000:], done.stderr[-2000:], "EXIT", done.returncode, flush=True)
    return True


kaggle_reference.run(llm=kbench.llm)
