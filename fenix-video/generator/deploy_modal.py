"""
Fenix Video — GPU deployment of the text-to-video engine on Modal.

The engine lives in worker.py and depends on no framework. This file only
supplies the GPU and the scaling policy, so the same engine also runs on a
Space, a rented box, or a local machine unchanged.

Deploy once:
    modal deploy fenix-video/generator/deploy_modal.py
"""
import modal

app = modal.App("fenix-video-gen")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.7.1",
        "diffusers>=0.36.0",
        "transformers>=4.51",
        "imageio[ffmpeg]",
        "accelerate",
        "huggingface-hub",
        "fastapi[standard]",
        "uvicorn",
    )
    .env({"HF_HOME": "/root/.cache/huggingface"})
)

_hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)


@app.function(
    image=image,
    gpu="T4",
    scaledown_window=300,
    timeout=1200,
    volumes={"/root/.cache/huggingface": _hf_cache},
)
@modal.asgi_app(label="fenix-video-gen")
def web():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from worker import app as engine

    return engine
