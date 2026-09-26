"""Publish one engine directory as a hosted Space.

Kept separate from deploy_spaces.sh so the shell script stays readable and the
upload logic is testable. Only the files a Space needs are uploaded, so a
changed engine never re-uploads the whole repository.

Each engine directory carries a SPACE_README.md whose front matter is what
makes the directory a Space; that file is required, not generated, so the
metadata is reviewable in the repository.
"""
import os
import sys


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: _publish_space.py <repo> <src_dir> <entry_file>")
        return 2
    repo, src, entry = sys.argv[1], sys.argv[2], sys.argv[3]

    from huggingface_hub import HfApi

    api = HfApi()
    try:
        api.create_repo(repo, repo_type="space", space_sdk="gradio", exist_ok=True)
    except Exception as e:  # noqa: BLE001 - creating twice must not be fatal
        print(f"  note: could not create the Space ({e}); trying to upload anyway")

    readme = os.path.join(src, "SPACE_README.md")
    if not os.path.exists(readme):
        raise SystemExit(f"missing {readme}")

    api.upload_folder(
        folder_path=src,
        repo_id=repo,
        repo_type="space",
        allow_patterns=["*.py", "*.txt", "SPACE_README.md"],
    )
    print(f"  uploaded {len(os.listdir(src))} files")
    print(f"  url: https://{repo.replace('/', '-').lower()}.hf.space")
    print("  In the Space settings, pick the ZeroGPU hardware, then wait for the build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
