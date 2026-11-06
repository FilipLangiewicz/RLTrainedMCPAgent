"""Check the access to the model proxy of Kaggle in a script job. This job calls no model and does not print the key."""
import json
import os
import subprocess
import sys
from pathlib import Path

report = {
    "proxy_url_set": "MODEL_PROXY_URL" in os.environ,
    "proxy_key_set": "MODEL_PROXY_API_KEY" in os.environ,
    "proxy_url": os.environ.get("MODEL_PROXY_URL"),
    "llm_default": os.environ.get("LLM_DEFAULT"),
    "llms_available": os.environ.get("LLMS_AVAILABLE"),
    "related_names": sorted(k for k in os.environ if any(w in k.upper() for w in ("PROXY", "LLM", "BENCHMARK"))),
}
try:
    result = subprocess.run([sys.executable, "-m", "pip", "show", "kaggle-benchmarks"], capture_output=True, text=True)
    report["library"] = [line for line in result.stdout.splitlines() if line.startswith(("Name", "Version"))]
    if report["proxy_url_set"] and report["proxy_key_set"]:
        from openai import OpenAI

        base = os.environ["MODEL_PROXY_URL"].removesuffix("/openapi").removesuffix("/genai") + "/openapi"
        client = OpenAI(api_key=os.environ["MODEL_PROXY_API_KEY"], base_url=base, max_retries=0)
        report["models"] = sorted(m.id for m in client.models.list())
except Exception as e:  # An error of the kernel deletes all output. The report must stay.
    report["error"] = f"{type(e).__name__}: {str(e)[:300]}"

text = json.dumps(report, indent=2)
print(text, flush=True)
Path("/kaggle/working/report.json").write_text(text)
