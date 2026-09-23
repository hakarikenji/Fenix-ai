# Fenix Music — Modal Generator (MusicGen)

GPU worker that turns text prompts into real audio (WAV). Deploys in 2 commands.

## Deploy (one-time)

```bash
pip install modal
modal token new                                   # first time only
modal secret create fenix-music-gen-secret MUSIC_GEN_TOKEN=<random-string>  # optional shared secret
modal deploy fenix-music/generator/worker.py
```

Modal prints the URL, e.g. `https://<workspace>--fenix-music-gen.modal.run`.

## Wire to the app

Set on the Fenix Music server environment:

```
MUSIC_GEN_URL=https://<workspace>--fenix-music-gen.modal.run
MUSIC_GEN_API_KEY=<same MUSIC_GEN_TOKEN>   # only if you created the secret
```

## Contract

`POST /` with JSON `{prompt, duration (5-30s), seed?}` → `audio/wav` bytes.
