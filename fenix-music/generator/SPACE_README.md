---
title: Fenix Music Engine
emoji: 🎹
colorFrom: amber
colorTo: red
sdk: gradio
pinned: false
license: other
app_file: space_app.py
---

# Fenix Music Engine

The **audio** half of the Fenix music engine, hosted so the app can reach a real
model without a GPU of its own.

The engine is `worker.py`. `space_app.py` is only the Gradio face a hosted Space
requires — the same engine also runs on a direct host with no changes.

## Settings to pick after the first build

| | |
|---|---|
| Hardware | ZeroGPU |
| SDK | Gradio (already set) |
| System packages | none |
| Secrets | none |

## The honest limits

- **Daily GPU allowance.** A free account gets a few GPU-minutes per day. A
  30-second track costs well under a second of GPU, so tracks are cheap; it is
  long generations that run the allowance down.
- **Cold starts.** The model loads on the first request, not at build time, so
  the first track after an idle period takes noticeably longer. Subsequent
  tracks do not.
- **Concurrency.** One generation at a time. Two callers queue rather than run
  in parallel.

The Fenix server reports the real state at `/api/music/generator-check`, so a
cold or refused host is visible instead of silent.
