"""Fenix Music Engine — Gradio face for a hosted GPU Space.

The engine is `worker.py` and has no Gradio dependency; this file exists only
because a hosted GPU Space must speak Gradio. Both faces call the same engine
loader, so a track sounds the same whichever host serves it.
"""
import os

import gradio as gr

from worker import MAX_DURATION, MODEL_ID, STEPS, _load_engines, wav_bytes

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = _load_engines()
    return _engine


def make(prompt, seconds, seed):
    gen = engine()
    if gen is None:
        raise gr.Error("the audio model could not load on this host")
    seconds = max(5, min(int(MAX_DURATION), int(seconds or 30)))
    seed = int(seed) if seed not in (None, "") else None
    return (gen(prompt, seconds, seed), "wav")


with gr.Blocks(title="Fenix Music Engine") as demo:
    gr.Markdown("# Fenix Music Engine\nHosted audio engine. Everything else in the app works without it.")
    with gr.Row():
        prompt = gr.Textbox(label="Prompt", lines=2,
                            placeholder="dark phonk beat, 140 BPM, distorted 808s, rain")
        seconds = gr.Slider(5, int(MAX_DURATION), value=30, step=5, label="Seconds")
    seed = gr.Number(label="Seed (optional)", precision=0)
    go = gr.Button("Generate", variant="primary")
    out = gr.Audio(label="Track", type="filepath")
    go.click(make, [prompt, seconds, seed], out, api_name="fenix_generate")

if __name__ == "__main__":
    demo.queue().launch()
