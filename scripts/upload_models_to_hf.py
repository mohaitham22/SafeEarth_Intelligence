"""Upload trained model .pkl files to the HuggingFace model repo.

The .pkl files are gitignored, so production (Render) downloads them from
HuggingFace at deploy time. After retraining, run this to push the new files
so the next deploy picks them up.

Auth (token is NEVER passed on the command line):
    1. Log in once in your terminal:  hf auth login   (or: huggingface-cli login)
       Paste a WRITE token from https://huggingface.co/settings/tokens
    2. The token is cached to disk; this script reads it automatically.
       (Or set HUGGINGFACE_TOKEN / HF_TOKEN in the environment.)

Usage:
    py -3.12 scripts/upload_models_to_hf.py <repo_id> [file1.pkl file2.pkl ...]

Examples:
    # Upload only the retrained impact regressor (default):
    py -3.12 scripts/upload_models_to_hf.py your-username/safeearth-models

    # Upload specific files:
    py -3.12 scripts/upload_models_to_hf.py your-username/safeearth-models \
        impact_regressor.pkl disaster_predictor.pkl
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

_SAVED_MODELS_DIR = Path(__file__).resolve().parent.parent / "backend" / "saved_models"
_DEFAULT_FILES = ["impact_regressor.pkl"]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("ERROR: missing <repo_id> argument.")
        return 2

    repo_id = sys.argv[1]
    filenames = sys.argv[2:] or _DEFAULT_FILES

    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or None
    api = HfApi(token=token)

    # Fail fast if not authenticated, with a clear hint.
    try:
        who = api.whoami()
        print(f"Authenticated as: {who.get('name', '<unknown>')}")
    except Exception as exc:  # noqa: BLE001
        print(
            "ERROR: not authenticated to HuggingFace.\n"
            "Run `hf auth login` (or `huggingface-cli login`) and paste a WRITE token,\n"
            "or set HUGGINGFACE_TOKEN in the environment.\n"
            f"Underlying error: {exc}"
        )
        return 1

    missing = [f for f in filenames if not (_SAVED_MODELS_DIR / f).exists()]
    if missing:
        print(f"ERROR: these files are missing under {_SAVED_MODELS_DIR}: {missing}")
        return 1

    print(f"Target repo: {repo_id}")
    for filename in filenames:
        local_path = _SAVED_MODELS_DIR / filename
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  Uploading {filename} ({size_mb:.1f} MB)...")
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=filename,
            repo_id=repo_id,
            repo_type="model",
            commit_message=f"Update {filename}",
        )
        print(f"  [ok] {filename} uploaded")

    print("Done. Trigger a Render redeploy (or push a commit) to fetch the new files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
