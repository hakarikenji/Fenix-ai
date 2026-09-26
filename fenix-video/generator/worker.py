"""
Fenix Video — text-to-video engine worker.

Turns one scene prompt into a real moving clip. Open-weight text-to-video
model, no API key, no per-request billing. Runs anywhere with a GPU: Modal,
a Hugging Face Space, a rented GPU box, or a machine with a local card.

The default checkpoint is the 1.3B text-to-video model, which is the size that
fits on a single consumer card. Point VIDEO_GEN_MODEL at a larger checkpoint
for more detail if the host has the VRAM.

Contract with the Fenix server (server.py /api/video/clip):
  GET  /            -> {"status", "engine", "model", "device", "ready"}
  POST /            -> {prompt, seconds (1-5), width, height, seed?} => video/mp4
  Optional shared secret: Authorization: Bearer <VIDEO_GEN_TOKEN>

Set on the Fenix server:
  VIDEO_GEN_URL      = the base URL this worker is served on
  VIDEO_GEN_API_KEY  = VIDEO_GEN_TOKEN, only if you created a secret
"""
import io
import os
import time

MODEL_ID = os.environ.get("VIDEO_GEN_MODEL", "Wan-AI/Wan2.1-T2V-1.3B-Diffusers")
MAX_SECONDS = int(os.environ.get("VIDEO_GEN_MAX_SECONDS", "5"))
STEPS = int(os.environ.get("VIDEO_GEN_STEPS", "20"))

_state = {"engine": None, "model": None, "device": None, "ready": False, "error": None}
_pipeline = None


def _device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _build_pipeline():
    """Load the text-to-video pipeline once and report the real device."""
    global _pipeline
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline

    dev = _device()
    pipe = WanPipeline.from_pretrained(
        MODEL_ID,
        vae=AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32),
        torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
    )
    pipe = pipe.to(dev)
    _pipeline = pipe
    _state.update(engine="text-to-video", model=MODEL_ID, device=dev, ready=True)
    print(f"fenix-video-engine READY model={MODEL_ID} device={dev}", flush=True)
    return pipe


def _encode_mp4(frames) -> bytes:
    """Wrap generated frames as an H.264 mp4 using the pipeline's own exporter."""
    import tempfile
    from diffusers.utils import export_to_video

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "clip.mp4")
        export_to_video(frames, path, fps=16)
        with open(path, "rb") as f:
            return f.read()


def generate_clip(prompt: str, seconds: float, width: int, height: int, seed) -> bytes:
    import torch

    pipe = _pipeline or _build_pipeline()
    if seed:
        torch.manual_seed(int(seed))
    # The model emits frames at a fixed rate; round to a whole frame count so
    # the clip length is exactly what was asked for.
    fps = 16
    num_frames = max(1, int(round(float(seconds) * fps)))
    result = pipe(
        prompt=prompt,
        num_frames=num_frames,
        height=int(height),
        width=int(width),
        num_inference_steps=STEPS,
        output_type="np",
    )
    frames = result.frames[0]
    return _encode_mp4(frames)


def looks_like_video(data: bytes) -> bool:
    """True when the bytes really are an mp4, not an HTML error page."""
    if not data or len(data) < 1000:
        return False
    if data[:4] in (b"RIFF", b"OggS", b"fLaC"):
        return False
    if data[4:8] == b"ftyp":
        return True
    if data[:5] in (b"<?xml", b"<html", b"<!DOC"):
        return False
    return True


def build_api():
    from fastapi import FastAPI, HTTPException, Request, Response

    api = FastAPI(title="fenix-video-engine", docs_url=None, redoc_url=None)

    def _authorize(request: Request) -> None:
        expected = os.environ.get("VIDEO_GEN_TOKEN", "").strip()
        if not expected:
            return
        if request.headers.get("authorization") != "Bearer " + expected:
            raise HTTPException(401, "bad or missing token")

    @api.get("/")
    @api.get("/health")
    async def health():
        return {
            "status": "ok" if _state["ready"] else ("error" if _state["error"] else "loading"),
            "service": "fenix-video-gen",
            "engine": _state["engine"],
            "model": _state["model"],
            "device": _state["device"],
            "ready": _state["ready"],
            "max_seconds": MAX_SECONDS,
        }

    @api.post("/")
    async def clip(request: Request):
        _authorize(request)
        body = await request.json()
        body = body or {}
        prompt = (body.get("prompt") or "").strip()[:800]
        if not prompt:
            raise HTTPException(400, "prompt is empty")
        try:
            seconds = float(body.get("seconds") or 4)
        except (TypeError, ValueError):
            seconds = 4.0
        seconds = max(1.0, min(float(MAX_SECONDS), seconds))
        width = max(256, min(1280, int(body.get("width") or 832)))
        height = max(256, min(1280, int(body.get("height") or 480)))
        seed = body.get("seed")

        if _state["device"] is None and _state["error"] is None:
            try:
                _build_pipeline()
            except Exception as e:  # noqa: BLE001
                _state["error"] = f"{type(e).__name__}: {e}"
        if _state["error"]:
            raise HTTPException(503, f"engine unavailable: {_state['error']}")

        started = time.time()
        try:
            data = generate_clip(prompt, seconds, width, height, seed)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"generation failed: {e}") from e
        if not looks_like_video(data):
            raise HTTPException(502, "engine returned no video")
        return Response(
            content=data,
            media_type="video/mp4",
            headers={"X-Fenix-Seconds": str(round(time.time() - started, 1))},
        )

    return api


app = build_api()


if __name__ == "__main__":
    import uvicorn

    # Loaded on first request, not at boot: a cold deploy should still answer
    # a health check immediately.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
