"""
Fenix Music — GPU deployment of the audio engine on Modal.

The engine itself lives in worker.py and has no Modal dependency. This file
only supplies the GPU and the scaling policy, so the same engine can also run
on a Space, a VPS, or a local machine with no code change.

Deploy once:
    modal deploy fenix-music/generator/deploy_modal.py
"""
import modal

app = modal.App("fenix-music-gen")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.7.1",
        "torchaudio==2.7.1",
        "transformers>=5.8.0",
        "numpy>=2.2.6",
        "einops>=0.8.2",
        "einops-exts>=0.0.4",
        "soundfile>=0.13.1",
        "huggingface-hub>=1.7.1",
        "fastapi[standard]",
        "uvicorn",
    )
    .apt_install("git")
    # The open-weight audio engine ships from its repository, not PyPI.
    .pip_install("git+https://github.com/Stability-AI/stable-audio-3.git")
    .env({"HF_HOME": "/root/.cache/huggingface"})
)

_hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)


@app.function(
    image=image,
    gpu="T4",
    scaledown_window=300,   # stay warm 5 minutes so the next track is fast
    timeout=900,
    volumes={"/root/.cache/huggingface": _hf_cache},
    min_containers=0,
)
@modal.asgi_app(label="fenix-music-gen")
def web():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from worker import app as engine

    return engine
