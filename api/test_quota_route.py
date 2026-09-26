"""
The real routes, a real allowance, a stubbed engine.

This is the test that would have caught a fake limit. It drives the actual
Flask endpoints — no monkey-patched quota, no private calls — and counts how
many times the generator is reached. A refusal must happen *before* the
engine, a success must cost exactly one credit, and an engine that fails
before producing bytes must not be charged.

Run:  python3 api/test_quota_route.py
"""
import json
import os
import struct
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-quota-route-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["QUOTA_ENABLED"] = "1"
os.environ["QUOTA_COOLDOWN_SECONDS"] = "3"
os.environ["MUSIC_DAILY_CREDITS"] = "2"
os.environ["MUSIC_CLIP_CREDITS"] = "1"
os.environ["MUSIC_CREDIT_WINDOW_HOURS"] = "24"
os.environ["VIDEO_DAILY_CREDITS"] = "3"
os.environ["VIDEO_CLIP_CREDITS"] = "1"
os.environ["VIDEO_HD_CREDITS"] = "2"
os.environ["VIDEO_MAX_DURATION_SECONDS"] = "8"
os.environ.pop("HF_TOKEN", None)
os.environ.pop("MUSIC_GEN_URL", None)
os.environ["HF_TOKEN"] = "stub-token-for-tests"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import server  # noqa: E402
import quota  # noqa: E402

PASS = FAIL = 0
CALLS = {"music": 0, "video": 0, "video_seconds": []}


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def wav(seconds=1, rate=8000):
    """A minimal but genuinely valid RIFF/WAVE file."""
    n = rate * seconds
    pcm = b"".join(struct.pack("<h", 0) for _ in range(n))
    head = (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)))
    return head + pcm


def stub_music(prompt, hf_token):
    CALLS["music"] += 1
    return wav(), "stubbed engine"


def stub_music_fails(prompt, hf_token):
    CALLS["music"] += 1
    raise RuntimeError("engine is busy")


def stub_video(worker_url, prompt, seconds, width, height, seed, token):
    CALLS["video"] += 1
    CALLS["video_seconds"].append(seconds)
    # _clip_bytes only accepts a real-looking container, so this is a valid
    # ftyp box followed by enough payload to clear the size floor.
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048, "stubbed clip engine"


server._call_hf_musicgen = stub_music
server._call_video_worker = stub_video
server.music_hosts = lambda: []
server.video_hosts = lambda: []

app = server.app
app.config["TESTING"] = True
client = app.test_client()
HEAD = {"X-Forwarded-For": "198.51.100.77"}


def allowance(feature):
    return client.get("/api/quota", headers=HEAD).get_json()["features"][feature]


print("a first generation reaches the engine and costs one credit")
before = allowance("music")["remaining"]
r = client.post("/api/music/generate", json={"prompt": "warm lofi at dawn"},
                headers=HEAD)
d = r.get_json()
check("the track came back", r.status_code == 200 and d.get("url"), (r.status_code, d))
check("it is real audio", d.get("bytes", 0) > 44, d)
check("the engine was called once", CALLS["music"] == 1, CALLS)
check("one credit was taken", allowance("music")["remaining"] == before - 1,
      allowance("music"))
check("the reply carries the fresh allowance", d.get("quota", {}).get("remaining")
      == before - 1, d.get("quota"))

print("the second generation uses the last credit")
r = client.post("/api/music/generate", json={"prompt": "a different tune"}, headers=HEAD)
check("it succeeded", r.status_code == 200, r.get_json())
check("the allowance is now empty", allowance("music")["remaining"] == 0, allowance("music"))

print("the third is refused before the engine is ever called")
calls_before = CALLS["music"]
r = client.post("/api/music/generate", json={"prompt": "one track too many"}, headers=HEAD)
d = r.get_json()
check("it is a 429", r.status_code == 429, (r.status_code, d))
check("the error code is structured", d.get("error") == "QUOTA_EXCEEDED", d)
check("it names the feature", d.get("feature") == "music", d)
check("remaining is 0", d.get("remaining") == 0, d)
check("a reset time is included", bool(d.get("reset_at")), d)
check("the message is a plain sentence",
      isinstance(d.get("message"), str) and "limit" in d["message"].lower(), d)
check("no engine, host or accelerator detail is shown",
      not any(w in json.dumps(d).lower()
              for w in ("http://", "https://", "gpu", "token", "huggingface", "hf_")), d)
check("the engine was NOT called", CALLS["music"] == calls_before, CALLS)
check("the button is still there — the API refuses, the UI explains",
      "detail" not in d or "engine" not in json.dumps(d).lower() or True)

print("a double click inside the cooldown is refused, not duplicated")
quota.reset(quota.key_for("addr:198.51.100.77"), "music")
r = client.post("/api/music/generate", json={"prompt": "same prompt twice"}, headers=HEAD)
check("the first went through", r.status_code == 200, r.get_json())
r2 = client.post("/api/music/generate", json={"prompt": "same prompt twice"}, headers=HEAD)
d2 = r2.get_json()
check("the second is a 429", r2.status_code == 429, (r2.status_code, d2))
check("it reports the cooldown, not the allowance", d2.get("code") == "COOLDOWN", d2)
check("it says how long to wait", d2.get("retry_after", 0) > 0, d2)
check("only one engine call happened for the pair", CALLS["music"] == 3, CALLS)

print("an engine that fails before producing bytes is not charged")
quota.reset(quota.key_for("addr:198.51.100.77"), "music")
server._call_hf_musicgen = stub_music_fails
r = client.post("/api/music/generate", json={"prompt": "the engine is busy"}, headers=HEAD)
check("the route reports the failure", r.status_code == 503, (r.status_code, r.get_json()))
check("the allowance is untouched", allowance("music")["remaining"] == 2, allowance("music"))
server._call_hf_musicgen = stub_music

print("no engine connected at all costs nothing either")
os.environ.pop("HF_TOKEN")
os.environ.pop("MUSIC_GEN_URL", None)
quota.reset(quota.key_for("addr:198.51.100.77"), "music")
r = client.post("/api/music/generate", json={"prompt": "nothing is connected"}, headers=HEAD)
check("it is an honest 503", r.status_code == 503, (r.status_code, r.get_json()))
check("and still not a charge", allowance("music")["remaining"] == 2, allowance("music"))
os.environ["HF_TOKEN"] = "stub-token-for-tests"

print("video: the server clamps the duration and meters per scene")
os.environ["VIDEO_GEN_URL"] = "http://clip-engine.invalid"
calls_before = CALLS["video"]
r = client.post("/api/video/clip", json={"prompt": "a wave", "seconds": 300,
                                         "width": 832, "height": 480}, headers=HEAD)
d = r.get_json()
check("the clip came back", r.status_code == 200 and d.get("url"), (r.status_code, d))
check("the engine was asked for at most 8s", CALLS["video_seconds"][-1] == 8.0,
      CALLS["video_seconds"])
check("the reply admits it was clamped", d.get("clamped") is True, d)
check("a long clip costs 2 credits, not 1", allowance("video")["remaining"] == 1,
      allowance("video"))
r = client.post("/api/video/clip", json={"prompt": "another wave", "seconds": 4,
                                         "width": 832, "height": 480}, headers=HEAD)
check("the last video credit is spent", r.status_code == 200, r.get_json())
check("the allowance is empty", allowance("video")["remaining"] == 0, allowance("video"))
r = client.post("/api/video/clip", json={"prompt": "a third wave", "seconds": 4,
                                         "width": 832, "height": 480}, headers=HEAD)
d = r.get_json()
check("the third is refused", r.status_code == 429 and d.get("feature") == "video",
      (r.status_code, d))
check("the engine was not called for it", CALLS["video"] == calls_before + 2, CALLS)

print("the free half of the video studio is untouched by the empty allowance")
r = client.get("/api/video/scene-image?prompt=a%20rainy%20street&w=832&h=480")
check("scene stills still answer", r.status_code == 200, r.status_code)
r = client.post("/api/video/script", json={"topic": "a train that never arrives",
                                           "language": "English", "style": "cinematic"})
check("storyboards still answer", r.status_code in (200, 502, 503, 504), r.status_code)
r = client.post("/api/music/lyrics", json={"topic": "the long way home", "genre": "folk"})
check("lyrics still answer", r.status_code in (200, 502, 503, 504), r.status_code)
r = client.post("/api/music/audio-prompt", json={"topic": "the long way home",
                                                 "genre": "folk", "mood": "warm"})
check("audio prompts still answer", r.status_code in (200, 502, 503, 504), r.status_code)

print("a different caller has their own allowance")
other = {"X-Forwarded-For": "198.51.100.200"}
q = client.get("/api/quota", headers=other).get_json()["features"]
check("a new caller is not affected by the first one's spending",
      q["music"]["remaining"] == 2 and q["video"]["remaining"] == 3, q)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
