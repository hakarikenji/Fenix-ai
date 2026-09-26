"""Fenix Video Engine — Gradio face for a hosted GPU Space.

The engine is `worker.py`; this file exists only because a hosted GPU Space
must speak Gradio. Both faces call the same loader, so a clip looks the same
whichever host serves it.
"""
import gradio as gr

from worker import MAX_SECONDS, MODEL_ID, STEPS, _build_pipeline, generate_clip

if __name__ == "__main__":
    with gr.Blocks(title="Fenix Video Engine") as demo:
        gr.Markdown("# Fenix Video Engine\n"
                    "Real motion per scene. Without it the studio still ships stills, "
                    "captions and a music bed.")
        prompt = gr.Textbox(label="Prompt", lines=2,
                            placeholder="neon street in the rain, slow dolly forward")
        seconds = gr.Slider(1, int(MAX_SECONDS), value=4, step=1, label="Seconds")
        with gr.Row():
            width = gr.Slider(256, 1280, value=832, step=32, label="Width")
            height = gr.Slider(256, 1280, value=480, step=32, label="Height")
        seed = gr.Number(label="Seed (optional)", precision=0)
        go = gr.Button("Generate", variant="primary")
        out = gr.Video(label="Clip")

        def make(p, s, w, h, sd):
            clip = generate_clip(p, float(s), int(w), int(h), int(sd) if sd not in (None, "") else None)
            return clip

        go.click(make, [prompt, seconds, width, height, seed], out, api_name="fenix_generate")

    # Weights load inside the first request, not at boot, so a cold Space still
    # answers a health check immediately.
    demo.queue().launch()
