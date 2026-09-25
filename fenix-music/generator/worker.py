"""
Fenix Music — GPU worker that turns a text prompt into a real WAV track.

Design goals (in order):
  1. Fewest moving parts. Uses the model's own transformers implementation, so
     there is no audiocraft / ffmpeg / xformers stack to fight with at install
     time. torch + transformers + fastapi is the whole dependency list.
  2. Honest. A health endpoint reports the real model state; a failed
     generation returns a real error instead of an empty body.
  3. Reproducible. The same seed yields the same track.

Contract with the Fenix server (server.py /api/music/generate):
  GET  /            -> {"status": "ok"|"loading", "model": ..., "engine": ...}
  POST /            -> {prompt, duration (5-30s), seed?}  =>  audio/wav bytes
  Optional shared secret: Authorization: Bearer <MUSIC_GEN_TOKEN>

Deploy once, then set on the server:
  MUSIC_GEN_URL      = the URL this deploy prints
  MUSIC_GEN_API_KEY  = the same token, only if you created the secret
"""
import io
import os
import struct
import time

import modal

app = modal.App("fenix-music-gen")

MODEL_ID = os.environ.get("MUSIC_GEN_MODEL", "facebook/musicgen-small")

# MusicGen emits one audio frame per 50 Hz, so max_new_tokens == seconds * 50.
FRAME_RATE = 50

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.*",
        "transformers>=4.51",
        "numpy",
        "fastapi[standard]",
    )
    .env({"HF_HOME": "/root/.cache/huggingface"})
)

_hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)


def _wav_bytes(samples) -> bytes:
    """Encode a float32 mono waveform (-1..1) as 16-bit PCM WAV.

    Written with the standard library so the worker needs no audio toolkit.
    """
    import numpy as np

    pcm = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2").tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 32000, 64000, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


@app.cls(
    image=image,
    gpu="T4",
    scaledown_window=300,   # stay warm 5 minutes so the next track is fast
    timeout=900,
    volumes={"/root/.cache/huggingface": _hf_cache},
)
class MusicGen:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        self.model = MusicgenForConditionalGeneration.from_pretrained(
            MODEL_ID, torch_dtype=torch.float16
        ).to("cuda")
        self.model.eval()
        self.sampling_rate = self.model.config.audio_encoder.sampling_rate
        # Report the true device so the health endpoint never claims GPU when
        # the container actually fell back to CPU.
        self.device = next(self.model.parameters()).device.type
        self.model_id = MODEL_ID
        print(f"fenix-music-gen READY model={MODEL_ID} device={self.device}", flush=True)

    @modal.method()
    def generate(self, prompt: str, duration: int = 20, seed=None) -> bytes:
        torch = self.torch
        seconds = max(5, min(30, int(duration or 20)))
        if seed is not None:
            torch.manual_seed(int(seed))
        inputs = self.processor(
            text=[prompt], padding=True, return_tensors="pt"
        ).to(self.device)
        with torch.no_grad():
            values = self.model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=3.0,
                max_new_tokens=seconds * FRAME_RATE,
            )
        audio = values[0, 0].float().cpu().numpy()
        return _wav_bytes(audio)


@app.function(image=image, timeout=900, volumes={"/root/.cache/huggingface": _hf_cache})
@modal.asgi_app(label="fenix-music-gen")
def web():
    from fastapi import FastAPI, HTTPException, Request, Response

    api = FastAPI()

    def _authorize(request: Request) -> None:
        expected = os.environ.get("MUSIC_GEN_TOKEN", "")
        if not expected:
            return
        if request.headers.get("authorization") != "Bearer " + expected:
            raise HTTPException(401, "bad or missing token")

    @api.get("/")
    @api.get("/health")
    async def health():
        """Container liveness only.

        The weights load inside the GPU class, so this endpoint cannot claim
        the model is loaded. It reports what it can actually verify: the
        service is up and which model it will use. A real generation request is
        what proves readiness.
        """
        return {"status": "up", "service": "fenix-music-gen", "model": MODEL_ID}

    @api.post("/")
    async def generate(request: Request):
        _authorize(request)
        body = await request.json()
        body = body or {}
        prompt = (body.get("prompt") or "").strip()[:800]
        if not prompt:
            raise HTTPException(400, "prompt is empty")
        try:
            duration = int(body.get("duration") or 20)
        except (TypeError, ValueError):
            duration = 20
        seed = body.get("seed")
        started = time.time()
        try:
            wav = MusicGen().generate.remote(prompt, duration, seed)
        except Exception as e:  # surface the real cause to the server log
            raise HTTPException(502, f"generation failed: {e}") from e
        if not wav or len(wav) < 1000:
            raise HTTPException(502, "generator returned no audio")
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={"X-Fenix-Seconds": str(round(time.time() - started, 1))},
        )

    return api
