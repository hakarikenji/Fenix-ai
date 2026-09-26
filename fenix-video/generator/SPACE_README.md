---
title: Fenix Video Engine
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: gradio
pinned: false
license: apache-2.0
app_file: space_app.py
---

# Fenix Video Engine

The **clip** half of the Fenix video engine. It turns one scene prompt into real
motion; without it the studio still ships stills, captions and a music bed.

The engine is `worker.py`. `space_app.py` is only the Gradio face a hosted Space
requires — the same engine also runs on a direct host with no changes.

## Settings to pick after the first build

| | |
|---|---|
| Hardware | ZeroGPU |
| SDK | Gradio (already set) |
| System packages | `ffmpeg` (the mp4 exporter needs it) |
| Secrets | none |

## The honest limits

- **Daily GPU allowance.** A free account gets a few GPU-minutes per day. A
  4-second 480p clip is the expensive kind of job, so treat the allowance as
  the real budget: a handful of clips, not hundreds.
- **Cold starts.** Weights load on the first request, so the first clip after
  an idle period is much slower than the next one.
- **Length.** Clips are 1–5 seconds by design. A longer scene is several clips
  cut together, not one long generation.
- **Resolution.** 480p is the practical ceiling on a free allowance. The
  renderer upscales to the canvas.

The Fenix server reports the real state at `/api/video/clip-check`, and the
storyboard keeps its still frame on screen until a clip is ready — so a slow or
refused host never blocks a render.
