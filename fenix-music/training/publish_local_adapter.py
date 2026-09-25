"""Package and publish the locally trained Fenix Music adapter to Hugging Face.

This avoids Modal completely. It reads HF_TOKEN from the process environment
only; it does not read or modify .env files.

Usage:
  HF_TOKEN=hf_xxx python fenix-music/training/publish_local_adapter.py \
    --adapter-dir fenix-music/training/local-output/adapter
"""

from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-dir", default="fenix-music/training/local-output/adapter")
    parser.add_argument("--repo", default="Hakari66684/fenix-music-lora")
    parser.add_argument("--filename", default="fenix-music-adapter.zip")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is missing. Set it in the execution environment, not in Git.")

    adapter_dir = Path(args.adapter_dir).resolve()
    if not (adapter_dir / "adapter_config.json").is_file():
        raise FileNotFoundError(f"Not a PEFT adapter directory: {adapter_dir}")

    from huggingface_hub import HfApi

    zip_path = adapter_dir.parent / args.filename
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(adapter_dir.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(adapter_dir.parent))

    HfApi(token=token).upload_file(
        path_or_fileobj=str(zip_path),
        path_in_repo=args.filename,
        repo_id=args.repo,
        repo_type="model",
    )
    print(f"LOCAL_ADAPTER_PUBLISHED {args.repo}/{args.filename}", flush=True)


if __name__ == "__main__":
    main()
