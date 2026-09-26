#!/usr/bin/env bash
# Publish the Fenix engines as hosted Spaces — the $0 path.
#
# Creates (or updates) one Space per engine, then prints the two URLs to paste
# into the Fenix server environment. Run it once; rerun it after changing an
# engine.
#
# Requires: huggingface_hub (`pip install huggingface_hub`). You log in once
# with `hf auth login`, which opens a browser — no card, no billing.
#
#   HF_ACCOUNT=<your-hf-username> sh scripts/deploy_spaces.sh
set -eu

ACCOUNT="${HF_ACCOUNT:-}"
if [ -z "$ACCOUNT" ]; then
  echo "Set HF_ACCOUNT to your Hugging Face username, e.g."
  echo "  HF_ACCOUNT=your-name sh scripts/deploy_spaces.sh"
  exit 1
fi

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

command -v "$PY" >/dev/null || { echo "python3 not found"; exit 1; }
"$PY" -c "import huggingface_hub" 2>/dev/null || {
  echo "Install the uploader first:  pip install huggingface_hub"
  exit 1
}

publish() {
  # $1 = space name, $2 = source dir, $3 = entry file
  local space="$1" src="$2" entry="$3"
  local repo="$ACCOUNT/$space"
  echo "==> $repo"
  "$PY" "$ROOT/scripts/_publish_space.py" "$repo" "$ROOT/$src" "$entry"
}

publish fenix-music-engine fenix-music/generator space_app.py
publish fenix-video-engine fenix-video/generator space_app.py

cat <<EOF

Both Spaces are published. Set these on the Fenix server (Keys tab):

  MUSIC_GEN_SPACE_URL = https://$ACCOUNT-fenix-music-engine.hf.space
  VIDEO_GEN_SPACE_URL = https://$ACCOUNT-fenix-video-engine.hf.space

Then check the wiring:
  /api/music/generator-check
  /api/video/clip-check

A Space sleeps when nobody calls it, and the free tier has a daily GPU
allowance. The first request after a sleep pays the wake-up, so a cold call
can take a while — the app keeps the still frame on screen meanwhile.
EOF
