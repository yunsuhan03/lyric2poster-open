"""Optional: mirror data/ to a Hugging Face Dataset repo so classmates can load the chart history.

  HF_TOKEN=hf_...  python scripts/push_to_hf.py  <user>/<dataset-name>

Then anyone can:  from datasets import load_dataset
                  load_dataset("<user>/<dataset-name>", data_files="history/global.csv")
Only chart files are uploaded. No lyrics are ever stored by this project.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not os.environ.get("HF_TOKEN"):
        print("usage: HF_TOKEN=... python scripts/push_to_hf.py <user>/<dataset-name>", file=sys.stderr)
        return 2
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    repo_id = argv[1]
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    data = Path(__file__).resolve().parent.parent / "data"
    api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=str(data),
                      commit_message="Update chart data")
    print(f"uploaded {data} to https://huggingface.co/datasets/{repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
