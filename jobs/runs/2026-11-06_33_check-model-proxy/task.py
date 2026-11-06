"""Check the proxy of Kaggle inside a benchmark task. This task calls no model and does not print the key."""
import json
import os
import subprocess
import sys

import kaggle_benchmarks as kbench


@kbench.task(name="check_model_proxy")
def check_model_proxy(llm) -> bool:
    report = {
        "proxy_url": os.environ.get("MODEL_PROXY_URL"),
        "proxy_key_set": "MODEL_PROXY_API_KEY" in os.environ,
        "llm_default": os.environ.get("LLM_DEFAULT"),
        "llms_available": os.environ.get("LLMS_AVAILABLE"),
        "python": sys.version,
        "git": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
    }
    try:
        from openai import OpenAI

        base = os.environ["MODEL_PROXY_URL"].removesuffix("/openapi").removesuffix("/genai") + "/openapi"
        client = OpenAI(api_key=os.environ["MODEL_PROXY_API_KEY"], base_url=base, max_retries=0)
        report["models"] = sorted(m.id for m in client.models.list())[:60]
    except Exception as e:  # The report must stay after a failure.
        report["models_error"] = f"{type(e).__name__}: {str(e)[:300]}"
    print("REPORT " + json.dumps(report), flush=True)
    return True


check_model_proxy.run(llm=kbench.llm)
