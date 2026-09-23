"""
Fenix Music — Modal worker: MusicGen text-to-music on GPU.

Deploy once:
  modal secret create fenix-music-gen-secret MUSIC_GEN_TOKEN=<random-string>   # optional but recommended
  modal deploy fenix-music/generator/worker.py

Then set on the Fenix Music server:
  MUSIC_GEN_URL = https://<workspace>--fenix-music-gen.modal.run
  MUSIC_GEN_API_KEY = <same MUSIC_GEN_TOKEN>   # if the secret was created

Endpoint: POST {prompt, duration, seed?} → audio/wav bytes.
"""
import io

import modal

app = modal.App("fenix-music-gen")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.4.1",
        "transformers==4.40.2",
        "encodec",
        "audiocraft==1.3.0",
        "scipy",
        "numpy<2",
        "fastapi[standard]",
    )
)


@app.cls(
    image=image,
    gpu="T4",
    scaledown_window=300,   # stay warm 5 min between tracks
    timeout=900,
)
class MusicGen:
    @modal.enter()
    def load(self):
        from audiocraft.models import MusicGen
        self.model = MusicGen.get_pretrained("facebook/musicgen-small")
        self.model.set_generation_params(duration=20)

    @modal.method()
    def generate(self, prompt: str, duration: int = 20, seed=None) -> bytes:
        import torchaudio
        self.model.set_generation_params(duration=max(5, min(30, duration)))
        if seed is not None:
            import torch
            torch.manual_seed(int(seed))
        wav = self.model.generate([prompt], progress=False)[0].cpu()
        buf = io.BytesIO()
        torchaudio.save(buf, wav, 32000, format="wav")
        return buf.getvalue()


@app.function(image=image, secrets=[
    modal.Secret.from_name("fenix-music-gen-secret", required_keys=[])
])
@modal.web_endpoint(method="POST", label="fenix-music-gen")
def generate_http(
    body: dict,
    authorization: str | None = None,
):
    """HTTP entry: {prompt, duration, seed?} → WAV bytes. Optional Bearer secret."""
    import os
    from fastapi import HTTPException, Response

    expected = os.environ.get("MUSIC_GEN_TOKEN", "")
    if expected and authorization != "Bearer " + expected:
        raise HTTPException(401, "bad token")
    prompt = (body.get("prompt") or "").strip()[:800]
    if not prompt:
        raise HTTPException(400, "prompt is empty")
    duration = max(5, min(30, int(body.get("duration") or 20)))
    seed = body.get("seed")
    wav = MusicGen().generate.remote(prompt, duration, seed)
    return Response(content=wav, media_type="audio/wav")
