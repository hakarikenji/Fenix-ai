# Fenix Video — text-to-video engine

Turns one scene prompt into a real moving clip. Open weights, no API key, no
per-request billing. This is the **clip** worker.

Without it, the video studio still works end to end: it writes the script,
fetches free scene images, burns captions, and mixes a music bed. What it
cannot do is produce motion. With a clip host, each scene becomes real video
instead of a still with a slow push-in.

## The engine

`worker.py` is the whole service — no framework dependency, so the same file
runs on Modal, a Hugging Face Space, a rented GPU box, or a local card.

Default checkpoint is the 1.3B text-to-video model (about 8GB VRAM, 480p,
5-second clips). Point `VIDEO_GEN_MODEL` at a larger checkpoint if the host
has the VRAM; the 14B models are far better and need far more.

## Run it

```bash
pip install -r requirements.txt
apt-get install -y ffmpeg      # the mp4 exporter needs it
python worker.py               # serves on $PORT, default 7860
```

On a GPU host with Modal:

```bash
pip install modal && modal token new
modal deploy fenix-video/generator/deploy_modal.py
```

A 1.3B clip takes roughly a minute on a T4, so this path is slower than the
image path. The studio keeps the still frame as the first-painted frame and
swaps in the clip when it is ready, so a slow clip never blocks a render.

## Wire to the app

```
VIDEO_GEN_URL     = https://<your-worker>
VIDEO_GEN_API_KEY = <same token>      # only if you set VIDEO_GEN_TOKEN
```

```
GET /api/video/clip-check          # reachability, without spending a clip
POST /api/video/clip               # {prompt, seconds, width, height, seed?}
```

## Contract

| | |
|---|---|
| `GET /` | `{"status", "engine", "model", "device", "ready", "max_seconds"}` |
| `POST /` | `{prompt, seconds (1–5), width, height, seed?}` → `video/mp4` bytes |

`seed` is optional; the same seed reproduces the same clip. Clips are served
back from `/clip/<name>`, and like audio they are only ever served for names
this server generated.
