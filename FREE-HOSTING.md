# Free hosting for the Fenix engines

The audio and video engines both need a GPU. This is the $0 path, with its
real limits written down rather than discovered later.

## What the engines need

| engine | checkpoint | hardware | per job |
|---|---|---|---|
| audio | Stable Audio 3, small | CPU works, GPU much better | well under a second of GPU for 30s |
| clip | Wan2.1 T2V-1.3B | GPU required, ~8GB | tens of seconds of GPU for 4s at 480p |

## The path: one hosted Space per engine

A free personal account can host two GPU Spaces. Both engines fit in those two
slots, so the whole thing runs for $0 with no card.

```bash
pip install huggingface_hub
hf auth login                     # opens a browser once
HF_ACCOUNT=<your-username> sh scripts/deploy_spaces.sh
```

Then, in each Space's settings, pick the **ZeroGPU** hardware. The script prints
the two URLs; set them on the Fenix server (Keys tab):

```
MUSIC_GEN_SPACE_URL = https://<you>-fenix-music-engine.hf.space
VIDEO_GEN_SPACE_URL = https://<you>-fenix-video-engine.hf.space
```

Check the wiring before generating anything:

```
/api/music/generator-check
/api/video/clip-check
```

### Why the engines are not Modal-locked

`worker.py` is a plain FastAPI service. The Space is only a Gradio face
(`space_app.py`) because a hosted GPU Space has to speak Gradio. The same engine
file, unchanged, also runs:

- directly — `python worker.py` on any box with a GPU
- on Modal — `modal deploy fenix-music/generator/deploy_modal.py`

So a hosted Space is a *place* to run the engine, not the engine itself. If the
free tier gets tighter, the same code moves somewhere else and only the URL
changes.

## The real limits

These are the numbers that decide whether the free tier is enough. They are
measured by the host, not by us, and they change — check the current figure
before relying on it.

| limit | effect |
|---|---|
| Daily GPU allowance (a few minutes on a free account) | tracks are cheap; **clips are not**. A 4s clip burns a visible slice. |
| Cold start | weights load on the first request, so the first job after an idle period is much slower. The app keeps the still frame on screen meanwhile. |
| Sleeps when idle | a space that nobody calls goes to sleep; the next call pays the wake-up |
| One job at a time | a second caller queues instead of running in parallel |
| Clip length 1–5s | a longer scene is several clips cut together, not one long generation |
| 480p in practice | the renderer upscales to the canvas |

If clips are the part you care about, that allowance is the number to watch.
Audio is comfortable on the free tier; video is the scarce one.

## What happens when there is no host

Nothing breaks. The app states the truth instead of pretending:

- Lyrics, audio prompts, music chat, the video script, scene images, captions
  and the export all work with no engine at all.
- The storyboard renders stills with crossfades and a Ken Burns move. Real
  motion is a separate, opt-in action.
- The UI never claims audio exists unless a real engine answered.

## The other free host, and why it is not the default

A free CPU Space (2 vCPU, 16GB) can host the audio engine's small checkpoint
with no GPU at all, and it has no daily allowance. Two reasons it is not the
default here:

1. Free CPU tier availability for *new* Spaces has been changing; assuming it is
   a plan, not a fact.
2. A CPU host is far slower, so a track that takes a second on a GPU takes
   minutes — which looks like a broken app rather than a working one.

Use it if the daily GPU allowance turns out to be the binding constraint. The
engine needs no change; publish `fenix-music/generator` as a CPU Space instead
and point `MUSIC_GEN_URL` at it.

## Local first

The fastest way to know whether an engine is worth hosting is to run it on your
own machine:

```bash
pip install -r fenix-music/generator/requirements.txt
python fenix-music/generator/worker.py
```

Then set `MUSIC_GEN_URL=http://localhost:7860`. A local box with a GPU has no
allowance, no queue, and no cold start — the exact opposite of the hosted path.
