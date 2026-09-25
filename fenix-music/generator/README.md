# Fenix Music — GPU audio worker (MusicGen)

Turns a text prompt into a real WAV track. This is the **audio** worker.
(The lyrics brain is a separate deployment — `music_brain_modal.py`.)

Everything else in Fenix Music works free today: lyrics, audio prompts, chat.
Only the audio itself needs this one-time worker.

## Deploy (one-time)

```bash
pip install modal
modal token new                 # first time only
modal deploy fenix-music/generator/worker.py
```

Deploy prints a URL, e.g. `https://<workspace>--fenix-music-gen.modal.run`.

Optional shared secret (recommended — stops anyone else spending your credit):

```bash
modal secret create fenix-music-gen-secret MUSIC_GEN_TOKEN=<random-string>
```

## Wire to the app

Set on the Fenix server environment (Keys tab):

```
MUSIC_GEN_URL     = https://<workspace>--fenix-music-gen.modal.run
MUSIC_GEN_API_KEY = <same token>      # only if you created the secret
```

Then check the wiring before generating anything:

```
GET /api/music/generator-check
```

It reports whether the URL is set, whether the worker answers, and — if not —
the exact reason (missing key, wrong secret, unreachable host).

## Contract

| | |
|---|---|
| `GET /` | `{"status": "up", "service": "fenix-music-gen", "model": ...}` |
| `POST /` | `{prompt, duration (5–30s), seed?}` → `audio/wav` bytes |

`seed` is optional; the same seed reproduces the same track.

`GET /` reports container liveness only — the weights load inside the GPU
class, so a health check cannot claim the model is loaded. One real
generation request is what proves readiness.

## Why these dependencies

`torch` + `transformers` only. The model ships its own transformers
implementation, so the worker does not need the `audiocraft` / `ffmpeg` /
`xformers` stack, which is the usual source of install failures. WAV encoding
is done with the Python standard library.

Defaults to `facebook/musicgen-small` (the small one). Override with
`MODEL_ID` if you need a different checkpoint.
