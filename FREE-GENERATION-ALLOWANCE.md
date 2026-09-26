# The free generation allowance

Fenix runs its own open models on limited compute, so the two expensive paths
are metered. Everything cheap stays unlimited on purpose: the free tier should
still let someone use the whole product, not punish them for trying it.

## What is free, always

| Feature | Metered? |
|---|---|
| Chat, streaming and the fallback reply | No |
| Research, memory, semantic recall, library | No |
| Coder, sandbox, tools, projects | No |
| Music **lyrics** | No |
| Music **audio prompt** (the sound design) | No |
| Music **radio host** chat | No |
| Video **script**, storyboard, shot planning | No |
| Video **scene stills** | No |
| Text-to-speech | No |
| **Music audio generation** | Yes |
| **Video motion rendering** (per scene) | Yes |

A limit is never a reason to remove a feature. Chat, research and the whole
storyboard half of the video studio are exactly as capable as before.

## The cost model

A credit is taken **at the moment the expensive inference is about to run**, not
when a screen is opened and not when a button is drawn.

* One audio track = 1 credit.
* One scene clip = 1 credit, or 2 if it is long (>5s) or high-resolution.

Anything the server refuses *before* the engine is reached — an empty prompt, no
engine connected, a request that would exceed the duration ceiling, a double
click inside the cooldown — costs nothing. If the engine is reached and then
fails without producing a file, the credit is returned. The only thing that
costs a credit is a real attempt at real generation.

## Default allowance

| | Credits | Window |
|---|---|---|
| Music | 3 | 24h |
| Video | 5 | 24h |

So: three tracks a day, and five scene clips a day (enough for a whole short
film at the default pacing).

## Configuration

All server-side, read at call time — change and restart, no code edits.

| Variable | Default | Meaning |
|---|---|---|
| `MUSIC_DAILY_CREDITS` | `3` | Music credits per window |
| `MUSIC_CLIP_CREDITS` | `1` | Cost of one audio track |
| `MUSIC_CREDIT_WINDOW_HOURS` | `24` | Music window length |
| `VIDEO_DAILY_CREDITS` | `5` | Video credits per window |
| `VIDEO_CLIP_CREDITS` | `1` | Cost of a standard scene clip |
| `VIDEO_HD_CREDITS` | `2` | Cost of a long / high-resolution clip |
| `VIDEO_HD_PIXELS` | `399360` | Pixel count that counts as high-res |
| `VIDEO_MAX_DURATION_SECONDS` | `10` | Hard ceiling on one clip |
| `VIDEO_CREDIT_WINDOW_HOURS` | `24` | Video window length |
| `QUOTA_COOLDOWN_SECONDS` | `5` | Repeat-submission cooldown |
| `QUOTA_ENABLED` | `1` | `0` disables metering entirely |

The windows are 1 hour to 30 days; a value outside that is clamped. To run a
weekly music allowance instead of a daily one, set
`MUSIC_CREDIT_WINDOW_HOURS=168` and `MUSIC_DAILY_CREDITS=21`.

## Identity

The account is the unit. A signed-in caller's key is a one-way hash of their
account token, so the allowance survives signing out, signing in again,
switching device, clearing `localStorage` and opening ten tabs. The APK and
signed-out browser path have no account, so those callers are keyed by a hash
of their network address.

Neither the token nor the address is ever written to disk. The browser is
never asked what it has left — it reads `GET /api/quota` and renders that, and
every generation reply carries a fresh copy. There is no client-side counter to
tamper with, no `localStorage` key that can be edited, and no URL parameter
that changes anything.

## API

`GET /api/quota` → what the caller has left, for both features:

```json
{
  "features": {
    "music": {"limit": 3, "used": 1, "remaining": 2, "unit_cost": 1,
              "window_seconds": 86400, "reset_at": 1790518379.4, "reset_in": 43200},
    "video": {"limit": 5, "used": 0, "remaining": 5, "unit_cost": 1, "window_seconds": 86400,
              "reset_at": 1790518379.4, "reset_in": 43200}
  },
  "enabled": true, "cooldown_seconds": 5
}
```

A refused generation answers `429` with the same shape everywhere:

```json
{
  "error": "QUOTA_EXCEEDED",
  "code": "QUOTA_EXCEEDED",
  "feature": "video",
  "remaining": 0,
  "limit": 5,
  "reset_at": "2026-09-27T14:14:15Z",
  "reset_in": 43200,
  "retry_after": 0,
  "message": "Your free generation limit has been reached. Your next video scene becomes available in 12.0h."
}
```

A double click inside the cooldown answers `429` with `"code": "COOLDOWN"` and
a `retry_after` in seconds. Engine, host and accelerator details are never in
either body — they stay in the server log.

## Where the code is

* `api/quota.py` — the whole service: config, ledger, atomic reserve, settle.
  One `BEGIN IMMEDIATE` transaction per reservation, so a burst of parallel
  requests can never take the same last credit twice.
* `server.py` — `_quota_caller()`, `_quota_error()` and the two enforcement
  points: `/api/music/generate` and `/api/video/clip`. `/api/quota` is
  read-only.
* `web/index_new.html` — the usage line, the countdown and the one-sentence
  explanation of a refusal.

## Tests

```
python3 api/test_quota.py        # 61 checks — the twelve required behaviours
python3 api/test_quota_route.py  # 38 checks — the real routes, stubbed engine
python3 api/test_quota_live.py   # 13 checks — the running server over HTTP
```

`test_quota_route.py` counts how many times the stubbed engine is reached, which
is what makes "the refusal happens before inference" a checked fact rather than
a claim. Run it with the rest:

```
for t in api/test_*.py; do python3 "$t" || echo "FAILED $t"; done
```
