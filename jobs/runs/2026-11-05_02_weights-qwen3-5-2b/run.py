"""Download the weights of one model from Hugging Face.

Write the commit and the SHA-256 of each file into manifest.json.
"""
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

MODEL = "Qwen/Qwen3.5-2B"
FOLDER = "qwen3.5-2b"
OUTPUT = Path("/kaggle/working") / FOLDER

# Only the gated models need the secret.
try:
    from kaggle_secrets import UserSecretsClient

    token = UserSecretsClient().get_secret("HF_TOKEN")
except Exception:  # noqa: BLE001  No secret is attached.
    token = None

# Resolve the commit first. Then the manifest and the files have the same revision.
commit = HfApi().model_info(MODEL, token=token).sha
print("model", MODEL, "commit", commit, flush=True)
snapshot_download(
    MODEL, revision=commit, local_dir=OUTPUT, token=token,
    ignore_patterns=["*.gguf", "*.bin", "*.pt", "*.h5", "*.msgpack", "original/*", ".cache/*"],
)

files = {}
for path in sorted(p for p in OUTPUT.rglob("*") if p.is_file() and ".cache" not in p.parts):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    files[str(path.relative_to(OUTPUT))] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}

manifest = {"model": MODEL, "commit": commit, "files": files}
(OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("files", len(files), "bytes", sum(f["bytes"] for f in files.values()), flush=True)
