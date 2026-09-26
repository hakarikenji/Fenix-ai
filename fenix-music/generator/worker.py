"""
Fenix Music — audio engine worker.

Turns a text prompt into a real WAV track. Runs anywhere that can reach the
network: Modal, a Hugging Face Space, a VPS, or the user's own machine.
There is no framework lock-in — the same file is the whole service.

Engines (pick with MUSIC_GEN_ENGINE):
  stable-audio-3  open-weight text-to-music diffusion model. The small
                  checkpoint runs on plain CPU; the medium one wants CUDA.
  musicgen         the older text-to-music model, kept as a fallback so a
                  machine that cannot install the new engine still makes music.
  auto            try stable-audio-3, fall back to musicgen.

Contract with the Fenix server (server.py /api/music/generate):
  GET  /            -> {"status", "engine", "model", "device", "ready"}
  POST /            -> {prompt, duration (5-120s), seed?}  =>  audio/wav bytes
  Optional shared secret: Authorization: Bearer <MUSIC_GEN_TOKEN>

Set on the Fenix server:
  MUSIC_GEN_URL      = the base URL this worker is served on
  MUSIC_GEN_API_KEY  = MUSIC_GEN_TOKEN, only if you created a secret
"""
import os
import struct
import time
import wave

MODEL_ID = os.environ.get("MUSIC_GEN_MODEL", "").strip()
ENGINE = os.environ.get("MUSIC_GEN_ENGINE", "auto").strip().lower()
DEFAULT_DURATION = int(os.environ.get("MUSIC_GEN_DURATION", "30"))
MAX_DURATION = int(os.environ.get("MUSIC_GEN_MAX_SECONDS", "120"))
STEPS = int(os.environ.get("MUSIC_GEN_STEPS", "8"))

# MusicGen emits one audio frame per 50 Hz.
MUSICGEN_FRAME_RATE = 50

_state = {"engine": None, "model": None, "device": None, "ready": False, "error": None}


def _device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def wav_bytes(samples, sample_rate: int, channels: int) -> bytes:
    """Encode a float waveform as 16-bit PCM WAV using only the stdlib.

    A model that hands back a quiet track is worse than useless in a video
    mix, so the signal is peak-normalised before it is written.
    """
    import numpy as np

    a = np.asarray(samples, dtype="float32")
    a = np.squeeze(a)
    if a.ndim == 2:
        # Models return (channels, samples); the WAV wants (samples, channels).
        a = a.T
    a = a.reshape(-1, 1) if a.ndim == 1 else a
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 1.0:
        a = a * (0.97 / peak)
    pcm = (np.clip(a, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(max(1, int(channels)))
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------- engines ---

def _load_stable_audio_3():
    """Load the open-weight Stable Audio 3 family. Returns a generate() handle."""
    from stable_audio_3 import StableAudioModel

    dev = _device()
    name = MODEL_ID or ("medium" if dev == "cuda" else "small-music")
    model = StableAudioModel.from_pretrained(name, device=dev)
    _state.update(engine="stable-audio-3", model=name, device=dev, ready=True)

    def generate(prompt: str, seconds: int, seed):
        out = model.generate(
            prompt=prompt,
            duration=float(seconds),
            steps=STEPS,
            seed=int(seed) if seed else -1,
        )
        rate = int(getattr(model.model, "sample_rate", 44100) or 44100)
        channels = int(getattr(model.model, "io_channels", 2) or 2)
        return wav_bytes(out, rate, channels)

    return generate


def _load_musicgen():
    """Fallback engine: the previous Fenix audio model."""
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    name = MODEL_ID or "facebook/musicgen-small"
    dev = _device()
    dtype = torch.float16 if dev == "cuda" else torch.float32
    processor = AutoProcessor.from_pretrained(name)
    model = MusicgenForConditionalGeneration.from_pretrained(name, torch_dtype=dtype)
    if dev == "cuda":
        model = model.to("cuda")
    model.eval()
    _state.update(engine="musicgen", model=name, device=dev, ready=True)

    def generate(prompt: str, seconds: int, seed):
        if seed:
            torch.manual_seed(int(seed))
        inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(dev)
        with torch.no_grad():
            values = model.generate(**inputs, do_sample=True, guidance_scale=3.0,
                                    max_new_tokens=seconds * MUSICGEN_FRAME_RATE)
        return wav_bytes(values[0, 0].float().cpu().numpy(), 32000, 1)

    return generate


def _load_engines():
    """Build the generate() handle for the configured engine.

    Order matters: the newer engine is tried first, and a failure is reported
    rather than silently producing something else.
    """
    order = {
        "stable-audio-3": [_load_stable_audio_3],
        "musicgen": [_load_musicgen],
        "auto": [_load_stable_audio_3, _load_musicgen],
    }.get(ENGINE, [_load_stable_audio_3, _load_musicgen])
    failures = []
    for load in order:
        try:
            return load()
        except Exception as e:  # noqa: BLE001 - the next engine gets a turn
            failures.append(f"{load.__name__}: {type(e).__name__}: {e}")
    _state["error"] = " | ".join(failures)
    return None


_generate = None


def build_api():
    from fastapi import FastAPI, HTTPException, Request, Response

    api = FastAPI(title="fenix-music-engine", docs_url=None, redoc_url=None)

    def _authorize(request: Request) -> None:
        expected = os.environ.get("MUSIC_GEN_TOKEN", "").strip()
        if not expected:
            return
        if request.headers.get("authorization") != "Bearer " + expected:
            raise HTTPException(401, "bad or missing token")

    @api.get("/")
    @api.get("/health")
    async def health():
        # Reports what it can actually verify. Weights load on the first
        # request, so a green health check means "engine compiled", not
        # "model resident" — the server still validates every reply as audio.
        return {
            "status": "ok" if _state["ready"] else ("error" if _state["error"] else "loading"),
            "service": "fenix-music-gen",
            "engine": _state["engine"],
            "model": _state["model"],
            "device": _state["device"],
            "ready": _state["ready"],
            "max_seconds": MAX_DURATION,
        }

    @api.post("/")
    async def generate(request: Request):
        global _generate
        _authorize(request)
        body = await request.json()
        body = body or {}
        prompt = (body.get("prompt") or "").strip()[:800]
        if not prompt:
            raise HTTPException(400, "prompt is empty")
        try:
            seconds = int(body.get("duration") or DEFAULT_DURATION)
        except (TypeError, ValueError):
            seconds = DEFAULT_DURATION
        seconds = max(5, min(MAX_DURATION, seconds))
        seed = body.get("seed")

        if _generate is None:
            _generate = _load_engines()
        if _generate is None:
            raise HTTPException(503, f"no engine could load: {_state['error']}")

        started = time.time()
        try:
            wav = _generate(prompt, seconds, seed)
        except Exception as e:  # noqa: BLE001 - the server logs the real cause
            raise HTTPException(502, f"generation failed: {e}") from e
        if not wav or len(wav) < 1000:
            raise HTTPException(502, "engine returned no audio")
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={
                "X-Fenix-Seconds": str(round(time.time() - started, 1)),
                "X-Fenix-Engine": str(_state["engine"]),
            },
        )

    return api


app = build_api()


if __name__ == "__main__":
    import uvicorn

    # Weights are large; loading them at boot makes a cold deploy a slow
    # deploy. Loading on first request keeps the service answering instantly
    # and lets the platform restart it freely.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
