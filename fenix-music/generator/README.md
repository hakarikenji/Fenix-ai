# Fenix Music — audio engine

Turns a text prompt into a real WAV track. This is the **audio** worker.
(The lyrics brain is a separate deployment — `music_brain_modal.py`.)

Everything else in Fenix Music works free today: lyrics, audio prompts, chat.
Only the audio file needs an engine host.

## The engine

`worker.py` is the whole service. It has no framework dependency, so the same
file runs on Modal, a Hugging Face Space, a VPS, or a local machine — only the
install list and the host differ.

| engine | model | hardware | notes |
|---|---|---|---|
| `stable-audio-3` | small | **plain CPU** | 433M, up to 120s |
| `stable-audio-3` | medium | CUDA GPU | 1.4B, up to 380s |
| `musicgen` | small | CPU or GPU | fallback engine |

Pick with `MUSIC_GEN_ENGINE` (`auto` tries the first, then the second). Leave
`MUSIC_GEN_MODEL` empty to get the sensible default for the detected device.

## Run it

Locally or on any box:

```bash
pip install -r requirements.txt
python worker.py            # serves on $PORT, default 7860
```

On a GPU host with Modal:

```bash
pip install modal && modal token new
modal deploy fenix-music/generator/deploy_modal.py
```

Both print a URL. Either way the app is the same.

## Wire to the app

Set on the Fenix server environment (Keys tab):

```
MUSIC_GEN_URL     = https://<your-worker>
MUSIC_GEN_API_KEY = <same token>      # only if you set MUSIC_GEN_TOKEN
```

Then check the wiring before generating anything:

```
GET /api/music/generator-check
```

It reports whether the URL is set, whether the engine answers, and — if not —
the exact reason (missing key, wrong secret, unreachable host).

## Contract

| | |
|---|---|
| `GET /` | `{"status", "engine", "model", "device", "ready", "max_seconds"}` |
| `POST /` | `{prompt, duration (5–120s), seed?}` → `audio/wav` bytes |

`seed` is optional; the same seed reproduces the same track.

The engine loads on the first request rather than at boot, so a cold deploy
still answers a health check instantly. A health check therefore reports
engine availability, not model residency — the server validates every reply as
real audio before serving it, so a bad reply is never handed to the browser.

## Optional shared secret

Stops anyone else spending your GPU credit:

```bash
export MUSIC_GEN_TOKEN=<random-string>   # on the worker host
export MUSIC_GEN_API_KEY=<same string>   # on the Fenix server
```
